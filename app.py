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


def has_gitlab_file_anywhere(project, base_names, branch="main", extensions=None):
    """
    Check for template files either in `.gitlab/` or `.gitlab/templates/`.
    """
    if extensions is None:
        extensions = ["", ".md", ".txt"]
    targets = {
        name.lower() + ext.lower() for name in base_names for ext in extensions
    }

    def files_in_path(path):
        try:
            items = project.repository_tree(path=path, ref=branch)
            return [item["name"].lower() for item in items]
        except Exception:
            return []

    files_gitlab = files_in_path(".gitlab")
    files_templates = files_in_path(".gitlab/templates")

    found_gitlab = any(filename in targets for filename in files_gitlab)
    found_templates = any(filename in targets for filename in files_templates)

    return found_gitlab or found_templates


def check_project_compliance(project, branch=None):
    required_files = {
        "README.md": ["README.md"],
        "CONTRIBUTING.md": ["CONTRIBUTING.md"],
        "CHANGELOG": ["CHANGELOG", "CHANGELOG.md", "CHANGELOG.txt"],
        "LICENSE": ["LICENSE", "LICENSE.md", "LICENSE.txt"],
    }
    report = {}
    try:
        branch = branch or getattr(project, "default_branch", None) or "main"
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]

        # Check for required files
        for label, variants in required_files.items():
            found = any(variant.lower() in filenames for variant in variants)
            report[label] = found

        # Check for .vscode/settings.json
        report["vscode_settings"] = check_vscode_settings(project, branch=branch)

        # Updated to check both .gitlab/ and .gitlab/templates/
        report["issue_templates"] = has_gitlab_file_anywhere(
            project,
            ["issue_template", "issues_template", "issue_templete", "issue_templates"],
            branch=branch,
            extensions=[".md"],
        )
        report["merge_request_templates"] = has_gitlab_file_anywhere(
            project,
            [
                "merge_request_template",
                "merge_requests_template",
                "merge_request_templete",
                "merge_requests_templete",
                "mr_template",
                "mrs_template",
                "mr_templete",
                "mrs_templete",
                "MR_Template",
            ],
            branch=branch,
            extensions=[".md"],
        )
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


def check_user_profile_readme(user_obj):  # user_obj must be from gl.users.get()
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
    suggestions = {
        "CONTRIBUTING.md": "Add a `CONTRIBUTING.md` file to guide collaborators on how to contribute to the project.",
        "CHANGELOG": "Maintain a `CHANGELOG.md` file to record changes across versions for better transparency.",
        "LICENSE": "Include a `LICENSE` file to define the legal usage of your project.",
        "issue_templates": "Add issue templates under `.gitlab/` or `.gitlab/templates/` folder as `.md` files like `issue_template.md`.",
        "merge_request_templates": "Add merge request templates under `.gitlab/` or `.gitlab/templates/` folder as `.md` files like `merge_request_template.md` or `MR_template.md`.",
        "description_present": "Provide a meaningful project description in GitLab settings.",
        "tags_present": "Tag your project releases for version control and clarity.",
        "README.md": "Add a `README.md` file at the root of the repository with setup and usage instructions.",
        "vscode_settings": "Add a `.vscode/settings.json` file to configure editor settings and ensure a consistent development environment.",
    }
    image_map = {
        "CONTRIBUTING.md": "Contributing.png",
        "CHANGELOG": "Changelog.png",
        "LICENSE": "license-example.png",
        "issue_templates": "issue-template.png",
        "merge_request_templates": "mr-template.png",
        "description_present": "project-description.png",
        "tags_present": "Tags.png",
        "README.md": "Readme.png",
        "vscode_settings": "vscode-settings.png",  # Add this image in your assets folder if desired
    }
    missing_items = [
        key for key, status in report.items() if key != "error" and status is False
    ]
    if missing_items:
        if not report.get("issue_templates") or not report.get("merge_request_templates"):
            st.image(
                "assets/files.png",
                caption="Correct file structure inside `.gitlab/` directory",
            )
        st.subheader("📌 Suggestions for Missing Items")
        for key, status in report.items():
            if status is False and key in suggestions:
                st.markdown(f"❌ **{key}** — {suggestions[key]}")
                img_file = image_map.get(key)
                if img_file:
                    try:
                        st.image(f"assets/{img_file}")
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


# Initialize both clients
client = GitLabClient(base_url=URL, private_token=TOKEN)  # Only for user APIs
gl = Gitlab(URL, private_token=TOKEN)  # For all project/repository operations


st.title("GitLab Tools")


# ---- SIDEBAR MODE SELECTION ----
mode = st.sidebar.radio(
    "Select Mode",
    ["Check Project Compliance", "Check User Profile README", "Get User Info"],
)


# ---------- MODE: Project Compliance WITH BRANCH SELECTION ----------
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


    # --- UI for branch selection & compliance ---
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
                    key="branch_selector"
                )
            else:
                selected_branch = default_branch
                st.warning("No branches found, will check default/main branch if possible.")


            run_check = st.button("Run Compliance Check on Selected Branch", key="run_compliance_check")
            run_automatic = (len(branches) == 1 and (branches[0] == default_branch))
            if run_check or run_automatic:
                report = check_project_compliance(project=project, branch=selected_branch)
                st.write(
                    f"### Project: {project.path_with_namespace} (ID: {project.id}) | Branch: `{selected_branch}`"
                )
                if "error" in report:
                    st.error(report["error"])
                else:
                    compliance_items = {k: v for k, v in report.items() if k != "error"}
                    for item, status in compliance_items.items():
                        emoji = "✅" if status else "❌"
                        st.markdown(f"- {emoji} **{item}**")
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
                    st.image("assets/Readme.png", caption="Profile README setup")
                elif has_readme:
                    branch = getattr(project, "default_branch", "main")
                    st.success("✅ Profile README project has `README.md`")
                    domain = urlparse(URL).netloc
                    url = f"https://{domain}/{project.path_with_namespace}/-/blob/{branch}/README.md"
                    st.markdown(f"[View README]({url})")
                else:
                    st.error("❌ Project exists but is missing `README.md`")
                    st.image("assets/Readme.png")
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
