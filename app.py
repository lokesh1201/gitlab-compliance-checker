import os
from urllib.parse import urlparse
import streamlit as st
from dotenv import load_dotenv
from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Project
from gitlab_utils.client import GitLabClient  # For user APIs only


# --------- Compliance check logic ---------
def check_vscode_settings(project, branch="main"):
    try:
        vscode_items = project.repository_tree(path=".vscode", ref=branch)
        filenames = [item["name"].lower() for item in vscode_items]
        return "settings.json" in filenames
    except Exception:
        return False


def list_markdown_files_in_folder(project, folder_path, branch="main"):
    """
    Returns list of markdown (.md) files in the folder_path on given branch.
    Returns empty list if folder doesn't exist or no .md files found.
    """
    try:
        items = project.repository_tree(path=folder_path, ref=branch)
        return [item["name"] for item in items if item["name"].lower().endswith(".md")]
    except Exception:
        return []


def list_files_in_root(project, branch="main"):
    """
    List files at the root directory of the project on given branch.
    """
    try:
        items = project.repository_tree(path="", ref=branch)
        return [item["name"].lower() for item in items]
    except Exception:
        return []


def check_templates_presence(project, branch="main"):
    """
    Checks .gitlab/issue_templates and .gitlab/merge_request_templates folders for presence and list .md files.
    Returns dict with booleans and lists.
    """
    result = {
        "issue_templates_folder": False,
        "issue_template_files": [],
        "merge_request_templates_folder": False,
        "merge_request_template_files": [],
    }

    issue_templates = list_markdown_files_in_folder(
        project, ".gitlab/issue_templates", branch
    )
    if issue_templates:
        result["issue_templates_folder"] = True
        result["issue_template_files"] = issue_templates

    mr_templates = list_markdown_files_in_folder(
        project, ".gitlab/merge_request_templates", branch
    )
    if mr_templates:
        result["merge_request_templates_folder"] = True
        result["merge_request_template_files"] = mr_templates

    return result


def check_project_compliance(project, branch=None):
    required_files = {
        "README.md": ["README.md"],
        "CONTRIBUTING.md": ["CONTRIBUTING.md"],
        "CHANGELOG": ["CHANGELOG", "CHANGELOG.md"],
        "LICENSE": ["LICENSE", "LICENSE.md"],
    }
    report = {}
    try:
        branch = branch or getattr(project, "default_branch", None) or "main"
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]

        # Check for required root files
        for label, variants in required_files.items():
            found = any(variant.lower() in filenames for variant in variants)
            report[label] = found

        # Check for .gitignore and pyproject.toml files at root
        report[".gitignore"] = ".gitignore" in filenames
        report["pyproject.toml"] = "pyproject.toml" in filenames

        # Check for .vscode/settings.json
        report["vscode_settings"] = check_vscode_settings(project, branch=branch)

        # New folder-level checks for templates presence and file lists
        template_details = check_templates_presence(project, branch=branch)
        report["issue_templates_folder"] = template_details["issue_templates_folder"]
        report["issue_template_files"] = template_details["issue_template_files"]
        report["merge_request_templates_folder"] = template_details[
            "merge_request_templates_folder"
        ]
        report["merge_request_template_files"] = template_details[
            "merge_request_template_files"
        ]

        # Project metadata
        report["description_present"] = bool(
            project.description and project.description.strip()
        )
        report["tags_present"] = len(project.tags.list(per_page=1)) > 0

    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"
    return report


def patch_gitlab_project():
    def check_compliance(self, branch=None):
        return check_project_compliance(self, branch=branch)

    Project.check_compliance = check_compliance


patch_gitlab_project()


def extract_path_from_url(input_str):
    try:
        parsed = urlparse(input_str)
        path = parsed.path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return input_str.strip()


def check_readme_in_project(project):
    try:
        branch = getattr(project, "default_branch", "main")
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]
        return "readme.md" in filenames
    except Exception as e:
        st.warning(f"Error checking README: {str(e)}")
        return False


def check_user_profile_readme(user_obj):
    try:
        projects = user_obj.projects.list(all=True)
        for project in projects:
            if project.name.strip().lower() == user_obj.username.strip().lower():
                full_project = gl.projects.get(project.id)
                return check_readme_in_project(full_project), full_project
        return False, None
    except Exception as e:
        st.warning(f"Error checking README for user {user_obj.username}: {e}")
        return False, None


# Utility: Get all branches of a project
def get_project_branches(project):
    try:
        branches = project.branches.list(all=True)
        return sorted([b.name for b in branches])
    except Exception:
        return []


# --------- Suggestion Helper ---------
def get_suggestions_for_missing_items(report):
    # Define suggestions in the desired sequence - order matters!
    ordered_items = [
        (
            "README.md",
            "Add a `README.md` file at the root of the repository with setup and usage instructions.",
            "Readme.png",
        ),
        (
            "CONTRIBUTING.md",
            "Add a `CONTRIBUTING.md` file to guide collaborators on how to contribute to the project.",
            "Contributing.png",
        ),
        (
            "CHANGELOG",
            "Maintain a `CHANGELOG.md` file to record changes across versions for better transparency.",
            "Changelog.png",
        ),
        (
            "LICENSE",
            "Include a `AGPLv3 LICENSE` file to define the legal usage of your project.",
            "license-example.png",
        ),
        (
            "issue_templates_folder",
            "Create `.gitlab/issue_templates/` and add `.md` templates like `Bug.md`, `Documentation.md`, or `Default.md`.",
            "issue_template_files.png",
        ),
        (
            "merge_request_templates_folder",
            "Create `.gitlab/merge_request_templates/` and add MR templates like `Bug.md`, `Documentation.md`, or `Default.md`.",
            "merge_request_files.png",
        ),
        (
            ".gitignore",
            "Add a `.gitignore` file to specify untracked files to ignore in your repository.",
            "gitignore.png",
        ),
        (
            "pyproject.toml",
            "Add a `pyproject.toml` file to declare Python build system requirements and project metadata.",
            "pyproject-toml.png",
        ),
        (
            "vscode_settings",
            "Add a `.vscode/settings.json` file to configure editor settings for consistency across contributors.",
            "vscode-settings.png",
        ),
        (
            "description_present",
            "Provide a meaningful project description in GitLab settings.",
            "project-description.png",
        ),
        (
            "tags_present",
            "Tag your project releases for version control and clarity.",
            "Tags.png",
        ),
    ]

    # Get missing items in the defined sequence
    missing_items = []
    for key, _, _ in ordered_items:
        if key in report and report[key] is False:
            missing_items.append(key)

    if missing_items:
        st.subheader("📌 Suggestions for Missing Items")

        files_image_shown = False

        for key, suggestion, image_file in ordered_items:
            if key in missing_items:
                st.markdown(f"❌ **{key}** — {suggestion}")

                # Show files.png right after issue_templates_folder suggestion
                if key == "issue_templates_folder" and not files_image_shown:
                    try:
                        st.image(
                            "assets/files.png",
                            caption="Recommended file structure inside `.gitlab/` directory",
                        )
                        files_image_shown = True
                    except Exception:
                        pass

                if image_file:
                    try:
                        st.image(f"assets/{image_file}")
                    except Exception:
                        pass
    else:
        if "error" not in report:
            st.success(
                "🎉 **All Set!** Your project meets all the compliance requirements."
            )


# --------- Main Streamlit App ---------
load_dotenv()
TOKEN = st.secrets.get("GITLAB_TOKEN") or os.getenv("GITLAB_TOKEN")
URL = st.secrets.get("GITLAB_URL") or os.getenv("GITLAB_URL")

if not TOKEN or not URL:
    st.error(
        "❌ GITLAB_TOKEN or GITLAB_URL not found. Please set them in secrets or .env."
    )
    st.stop()

client = GitLabClient(base_url=URL, private_token=TOKEN)  # For user APIs
gl = Gitlab(URL, private_token=TOKEN)  # For project APIs

st.title("GitLab Tools")

mode = st.sidebar.radio(
    "Select Mode",
    ["Check Project Compliance", "Check User Profile README", "Get User Info"],
)

# --- MODE: Check Project Compliance ---
if mode == "Check Project Compliance":
    st.subheader("📊 Project Compliance Checker")
    project_input = st.text_input(
        "Enter project path, URL, or project ID",
        key="project_compliance_input",
        on_change=lambda: setattr(
            st.session_state, "project_compliance_triggered", True
        ),
    )
    check_triggered = st.session_state.get("project_compliance_triggered", False)
    button_clicked = st.button("Check Compliance", key="project_compliance_button")

    if check_triggered or button_clicked:
        st.session_state["project_compliance_triggered"] = False
        input_str = project_input.strip()
        if not input_str:
            st.warning("Please enter a valid project path, URL or ID.")
            st.session_state["selected_project_id"] = None
            st.session_state["branches"] = []
        else:
            path_or_id = extract_path_from_url(input_str)
            is_id = path_or_id.isdigit()
            try:
                project = gl.projects.get(int(path_or_id) if is_id else path_or_id)
                st.session_state["selected_project_id"] = project.id
                branches = get_project_branches(project)
                st.session_state["branches"] = branches
            except GitlabGetError:
                st.error(f"Project '{path_or_id}' not found.")
                st.session_state["selected_project_id"] = None
                st.session_state["branches"] = []
            except Exception as e:
                st.error(f"Unexpected error: {str(e)}")
                st.session_state["selected_project_id"] = None
                st.session_state["branches"] = []

    selected_project_id = st.session_state.get("selected_project_id")
    branches = st.session_state.get("branches") or []

    if selected_project_id:
        try:
            project = gl.projects.get(selected_project_id)
            if not branches:
                branches = get_project_branches(project)
                st.session_state["branches"] = branches

            default_branch = getattr(project, "default_branch", "main")
            if default_branch in branches:
                default_idx = branches.index(default_branch)
            elif "main" in branches:
                default_idx = branches.index("main")
            else:
                default_idx = 0 if branches else None

            if branches:
                selected_branch = st.selectbox(
                    "Select branch for compliance check:",
                    branches,
                    index=default_idx if default_idx is not None else 0,
                    key="branch_selector",
                )
            else:
                selected_branch = default_branch
                st.warning(
                    "No branches found, will check default/main branch if possible."
                )

            run_check = st.button(
                "Run Compliance Check on Selected Branch", key="run_compliance_check"
            )
            run_automatic = len(branches) == 1 and (branches[0] == default_branch)

            if run_check or run_automatic:
                report = check_project_compliance(
                    project=project, branch=selected_branch
                )
                st.write(
                    f"### Project: {project.path_with_namespace} (ID: {project.id}) | Branch: `{selected_branch}`"
                )

                if "error" in report:
                    st.error(report["error"])
                else:
                    # --- CATEGORIZED COMPLIANCE REPORT ---
                    st.markdown("### 📋 Compliance Summary by Category")

                    categories = {
                        "1. 📄 Project Metadata": {
                            "description_present": "Project Description",
                            "tags_present": "Tags",
                        },
                        "2. 📚 Project Documentation": {
                            "README.md": "README.md",
                            "CONTRIBUTING.md": "CONTRIBUTING.md",
                            "CHANGELOG": "CHANGELOG / CHANGELOG.md",
                            "LICENSE": "LICENSE / LICENSE.md",
                            "issue_templates_folder": "Issue Templates Folder (.gitlab/issue_templates)",
                            "issue_template_files": "Issue Template Files",
                            "merge_request_templates_folder": "Merge Request Templates Folder (.gitlab/merge_request_templates)",
                            "merge_request_template_files": "Merge Request Template Files",
                        },
                        "3. ⚙️ Project Configuration": {
                            ".gitignore": ".gitignore",
                            "pyproject.toml": "pyproject.toml",
                            "vscode_settings": ".vscode/settings.json",
                        },
                    }

                    for category_title, items in categories.items():
                        # Increase font size and make bold
                        st.markdown(
                            f"<h4 style='font-size: 1.3em; font-weight: bold;'>{category_title}</h4>",
                            unsafe_allow_html=True,
                        )
                        with st.expander("Click to view details", expanded=True):
                            for key, display_name in items.items():
                                status = report.get(key, False)

                                if isinstance(status, list):
                                    count = len(status)
                                    emoji = "✅" if count > 0 else "❌"
                                    # Display ALL file names, no truncation
                                    listed = (
                                        ", ".join(sorted(status)) if status else "None"
                                    )
                                    st.markdown(
                                        f"{emoji} **{display_name}**: {count} file(s) ({listed})"
                                    )
                                else:
                                    emoji = "✅" if status else "❌"
                                    st.markdown(f"{emoji} **{display_name}**")

                    get_suggestions_for_missing_items(report)

        except Exception as e:
            st.error(f"Error loading project and branches: {e}")

# ---------- MODE: User Profile README ----------
elif mode == "Check User Profile README":
    st.subheader("✅ Check if user has a profile README project")
    user_input = st.text_input(
        "Enter GitLab username, user ID, or user profile URL",
        key="user_readme_input",
        on_change=lambda: setattr(st.session_state, "user_readme_triggered", True),
    )
    check_triggered = st.session_state.get("user_readme_triggered", False)
    button_clicked = st.button("Check README", key="user_readme_button")

    if check_triggered or button_clicked:
        st.session_state["user_readme_triggered"] = False
        input_val = user_input.strip()
        if not input_val:
            st.warning("Please enter a username, user ID or URL.")
        else:
            try:
                if input_val.isdigit():
                    user_obj = gl.users.get(int(input_val))
                else:
                    username = extract_path_from_url(input_val)
                    result = gl.users.list(username=username)
                    if not result:
                        raise Exception("User not found")
                    user_obj = result[0]

                st.write(
                    f"User: **{user_obj.name}** (@{user_obj.username}, ID: {user_obj.id})"
                )
                has_readme, project = check_user_profile_readme(user_obj)

                if project is None:
                    st.info(f"No profile project named `{user_obj.username}` found.")
                    st.markdown(
                        "💡 **Suggestion**: Create a project with your username and add `README.md`."
                    )
                    try:
                        st.image("assets/Readme.png", caption="Profile README setup")
                    except Exception:
                        pass
                elif has_readme:
                    branch = getattr(project, "default_branch", "main")
                    st.success("✅ Profile README project has `README.md`")
                    domain = urlparse(URL).netloc
                    url = f"https://{domain}/{project.path_with_namespace}/-/blob/{branch}/README.md"
                    st.markdown(f"[View README]({url})")
                else:
                    st.error("❌ Project exists but is missing `README.md`")
                    try:
                        st.image("assets/Readme.png")
                    except Exception:
                        pass
            except Exception as e:
                st.error(f"User not found or error occurred: {e}")

# ---------- MODE: Get User Info ----------
elif mode == "Get User Info":
    st.subheader("👤 User Info Lookup")
    user_input = st.text_input(
        "Enter GitLab username, user ID, or profile URL",
        key="user_info_input",
        on_change=lambda: setattr(st.session_state, "user_info_triggered", True),
    )
    check_triggered = st.session_state.get("user_info_triggered", False)
    button_clicked = st.button("Get User Info", key="user_info_button")

    if check_triggered or button_clicked:
        st.session_state["user_info_triggered"] = False
        input_val = user_input.strip()
        if not input_val:
            st.warning("Please enter a username, user ID or user profile URL.")
        else:
            try:
                if input_val.isdigit():
                    user = client.users.get_by_userid(int(input_val))
                else:
                    username = extract_path_from_url(input_val)
                    user = client.users.get_by_username(username)

                st.write(f"**Name:** {user['name']}")
                st.write(f"**Username:** @{user['username']}")
                st.write(f"**User ID:** {user['id']}")
                if user.get("avatar_url"):
                    st.image(user["avatar_url"], width=80)
                st.write(f"[View GitLab Profile]({user.get('web_url', '')})")

                # Account statistics
                st.markdown("#### 📊 Account Statistics")
                col1, col2 = st.columns(2)
                with col1:
                    proj_count = client.users.get_user_project_count(user["id"])
                    st.metric(
                        "Projects", proj_count if isinstance(proj_count, int) else "N/A"
                    )
                    group_count = client.users.get_user_group_count(user["id"])
                    st.metric(
                        "Groups", group_count if isinstance(group_count, int) else "N/A"
                    )
                with col2:
                    issue_count = client.users.get_user_issue_count(user["id"])
                    st.metric(
                        "Issues", issue_count if isinstance(issue_count, int) else "N/A"
                    )
                    mr_count = client.users.get_user_mr_count(user["id"])
                    st.metric(
                        "Merge Requests",
                        mr_count if isinstance(mr_count, int) else "N/A",
                    )

                # Show warnings if API calls failed
                for label, count in [
                    ("projects", proj_count),
                    ("groups", group_count),
                    ("issues", issue_count),
                    ("merge requests", mr_count),
                ]:
                    if isinstance(count, str) and count.startswith("Error:"):
                        st.warning(f"Could not get {label} count: {count[6:].strip()}")

            except Exception as e:
                st.error(f"User not found or error: {e}")
