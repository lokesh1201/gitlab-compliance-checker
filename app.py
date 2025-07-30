import os
from urllib.parse import urlparse
import streamlit as st
from dotenv import load_dotenv
from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Project
from gitlab_utils.client import GitLabClient  # For user APIs only


# --- Optimize: Cache file reads ---
@st.cache_data(ttl=60)
def read_file_content(_project, file_path, ref):
    try:
        file = _project.files.get(file_path=file_path, ref=ref)
        return file.decode().decode("utf-8")
    except Exception:
        return None


# --- Compliance Logic ---
def check_vscode_settings(project, branch="main"):
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return "settings.json" in [item["name"].lower() for item in items]
    except Exception:
        return False


def check_vscode_file_exists(project, filename, branch="main"):
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return filename.lower() in [item["name"].lower() for item in items]
    except Exception:
        return False


def check_license_content(project, branch="main"):
    """Strict check for AGPLv3 license"""
    content = read_file_content(project, "LICENSE", branch) or read_file_content(
        project, "LICENSE.md", branch
    )
    if not content:
        return "not_found"
    content_lower = content.lower().replace("-", "").replace(" ", "")
    if any(
        ind in content_lower
        for ind in [
            "gnuafferogeneralpubliclicense",
            "agpl3.0",
            "afferogeneralpubliclicenseversion3",
        ]
    ):
        return "valid"
    return "invalid"


def check_vscode_settings_content(project, branch="main"):
    """Check if settings.json has ruff"""
    content = read_file_content(project, ".vscode/settings.json", branch)
    if not content:
        return {"exists": False, "has_ruff": False}
    try:
        import json

        config = json.loads(content)
        has_ruff = (
            config.get("python", {}).get("linting", {}).get("provider") == "ruff"
            or "ruff" in str(config.get("python", {})).lower()
        )
        return {"exists": True, "has_ruff": has_ruff}
    except Exception:
        return {"exists": True, "has_ruff": False}


def list_markdown_files_in_folder(project, folder_path, branch="main"):
    try:
        items = project.repository_tree(path=folder_path, ref=branch)
        return [item["name"] for item in items if item["name"].lower().endswith(".md")]
    except Exception:
        return []


def check_templates_presence(project, branch="main"):
    result = {
        "issue_templates_folder": False,
        "issue_template_files": [],
        "merge_request_templates_folder": False,
        "merge_request_template_files": [],
    }
    try:
        items = project.repository_tree(path=".gitlab/issue_templates", ref=branch)
        md_files = [
            item["name"] for item in items if item["name"].lower().endswith(".md")
        ]
        if md_files:
            result["issue_templates_folder"] = True
            result["issue_template_files"] = md_files
    except Exception:
        pass
    try:
        items = project.repository_tree(
            path=".gitlab/merge_request_templates", ref=branch
        )
        md_files = [
            item["name"] for item in items if item["name"].lower().endswith(".md")
        ]
        if md_files:
            result["merge_request_templates_folder"] = True
            result["merge_request_template_files"] = md_files
    except Exception:
        pass
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
        branch = branch or getattr(project, "default_branch", "main")
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]

        for label, variants in required_files.items():
            report[label] = any(variant.lower() in filenames for variant in variants)

        report[".gitignore"] = ".gitignore" in filenames
        report["pyproject.toml"] = "pyproject.toml" in filenames
        report["vscode_settings"] = check_vscode_settings(project, branch)

        # Content checks
        license_status = check_license_content(project, branch)
        report["license_valid"] = license_status == "valid"
        report["license_status"] = license_status

        vscode_content = check_vscode_settings_content(project, branch)
        report["vscode_has_ruff"] = vscode_content["has_ruff"]
        report["vscode_config_exists"] = vscode_content["exists"]
        report["vscode_extensions_exists"] = check_vscode_file_exists(
            project, "extensions.json", branch
        )
        report["vscode_launch_exists"] = check_vscode_file_exists(
            project, "launch.json", branch
        )

        # Templates
        template_details = check_templates_presence(project, branch)
        report.update(template_details)

        # Metadata
        report["description_present"] = bool(
            project.description and project.description.strip()
        )
        report["tags_present"] = len(project.tags.list(per_page=1)) > 0

    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"
    return report


# Patch Project class
def patch_gitlab_project():
    Project.check_compliance = lambda self, branch=None: check_project_compliance(
        self, branch
    )


patch_gitlab_project()


def extract_path_from_url(input_str):
    try:
        path = urlparse(input_str).path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return input_str.strip()


def get_project_branches(project):
    try:
        branches = project.branches.list(all=True)
        return sorted([b.name for b in branches])
    except Exception:
        return []


# --- Suggestions Helper ---
def get_suggestions_for_missing_items(report):
    suggestion_list = [
        (
            "README.md",
            "Add a `README.md` file at the root of the repository with setup and usage instructions.",
        ),
        (
            "CONTRIBUTING.md",
            "Add a `CONTRIBUTING.md` file to guide collaborators on how to contribute to the project.",
        ),
        (
            "CHANGELOG",
            "Maintain a `CHANGELOG.md` file to record changes across versions for better transparency.",
        ),
        (
            "LICENSE",
            "Include a `AGPLv3 LICENSE` file to define the legal usage of your project.",
        ),
        (
            "license_valid",
            "Ensure the license is AGPLv3. Replace MIT/Apache with AGPLv3 for compliance.",
        ),
        (
            "issue_templates_folder",
            "Create `.gitlab/issue_templates/` and add `.md` templates like `Bug.md`, `Documentation.md`, or `Default.md`.",
        ),
        (
            "merge_request_templates_folder",
            "Create `.gitlab/merge_request_templates/` and add MR templates like `Bug.md`, `Documentation.md`, or `Default.md`.",
        ),
        (
            ".gitignore",
            "Add a `.gitignore` file to specify untracked files to ignore in your repository.",
        ),
        (
            "pyproject.toml",
            "Add a `pyproject.toml` file to declare Python build system requirements and project metadata.",
        ),
        (
            ".vscode/settings.json",
            "Add a `.vscode/settings.json` file to configure editor settings for consistency across contributors.",
        ),
        (
            "vscode_has_ruff",
            "Ensure `.vscode/settings.json` includes Ruff as the linter.",
        ),
        (
            "vscode_extensions_exists",
            "Add a `.vscode/extensions.json` file to configure recommended VSCode extensions.",
        ),
        (
            "vscode_launch_exists",
            "Add a `.vscode/launch.json` file to configure debug launch profiles in VSCode.",
        ),
        (
            "description_present",
            "Provide a meaningful project description in GitLab settings.",
        ),
        ("tags_present", "Tag your project releases for version control and clarity."),
    ]
    image_map = {
        "README.md": "Readme.png",
        "CONTRIBUTING.md": "Contributing.png",
        "CHANGELOG": "Changelog.png",
        "LICENSE": "license-example.png",
        "license_valid": "license-wrong.png",
        "issue_templates_folder": "issue_template_files.png",
        "merge_request_templates_folder": "merge_request_files.png",
        ".gitignore": "gitignore.png",
        "pyproject.toml": "pyproject-toml.png",
        ".vscode/settings.json": "vscode-settings.png",
        "vscode_has_ruff": "vscode-ruff.png",
        "vscode_extensions_exists": "vscode-extensions.png",
        "vscode_launch_exists": "vscode-launch.png",
        "description_present": "project-description.png",
        "tags_present": "Tags.png",
    }

    st.subheader("📌 Suggestions for Missing Items")

    # Only show files.png if template folders are missing
    show_files_image = not report.get(
        "issue_templates_folder", False
    ) or not report.get("merge_request_templates_folder", False)
    files_image_shown = False

    for key, suggestion_text in suggestion_list:
        if not report.get(key, True):  # If missing
            # Show files.png only once, before first template folder suggestion
            if (
                key in ["issue_templates_folder", "merge_request_templates_folder"]
                and show_files_image
                and not files_image_shown
            ):
                try:
                    st.image(
                        "assets/files.png",
                        caption="Recommended file structure inside `.gitlab/` directory",
                        width=500,
                    )
                    files_image_shown = True
                except Exception:
                    st.warning("Could not load: assets/files.png")

            st.markdown(f"❌ **{key}** — {suggestion_text}")

            # Show individual help image
            img_file = image_map.get(key)
            if img_file:
                try:
                    st.image(f"assets/{img_file}", width=400)
                except Exception:
                    pass


# --- VSCode & pyproject.toml Documentation Markdown ---
def render_vscode_and_pyproject_docs():
    st.markdown(
        """
### 🛠️ Documentation for `.vscode` Configuration Files and `pyproject.toml`

These files help maintain consistent development environment and build configurations across the team.

- [`.vscode/launch.json`](https://code.visualstudio.com/docs/editor/debugging#_launch-configurations)
  Defines debug launch profiles for running and debugging the project inside VSCode.

- [`.vscode/extensions.json`](https://code.visualstudio.com/docs/editor/extension-marketplace#_recommended-extensions)
  Lists recommended VSCode extensions to install for efficient coding and linting.

- [`.vscode/settings.json`](https://code.visualstudio.com/docs/getstarted/settings)
  Contains workspace-specific editor settings such as Python interpreter path, linters (e.g., Ruff), and environment management (`uv`).

- [`pyproject.toml`](https://peps.python.org/pep-0518/)
  Configuration for Python project build system, dependencies, and packaging metadata. Ensures reproducible builds and integration with tools like Poetry or Flit.
        """
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
        on_change=lambda: st.session_state.update(
            {"project_compliance_run": True, "project_compliance_triggered": True}
        ),
    )

    # Auto-trigger on Enter
    if st.session_state.get("project_compliance_run"):
        st.session_state["project_compliance_run"] = False
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
                            "license_valid": "LICENSE is AGPLv3",
                            "issue_templates_folder": "Issue Templates Folder (.gitlab/issue_templates)",
                            "issue_template_files": "Issue Template Files",
                            "merge_request_templates_folder": "Merge Request Templates Folder (.gitlab/merge_request_templates)",
                            "merge_request_template_files": "Merge Request Template Files",
                        },
                        "3. ⚙️ Project Configuration": {
                            ".gitignore": ".gitignore",
                            "pyproject.toml": "pyproject.toml",
                            "vscode_settings": ".vscode/settings.json",
                            "vscode_has_ruff": ".vscode/settings.json has Ruff",
                            "vscode_extensions_exists": ".vscode/extensions.json",
                            "vscode_launch_exists": ".vscode/launch.json",
                        },
                    }

                    all_passed = True
                    for category_title, items in categories.items():
                        st.markdown(
                            f"<h4 style='font-size: 1.3em; font-weight: bold;'>{category_title}</h4>",
                            unsafe_allow_html=True,
                        )
                        with st.expander("Click to view details", expanded=True):
                            for key, display_name in items.items():
                                status = report.get(key, False)

                                if key == "vscode_settings":
                                    display_name = ".vscode/settings.json"

                                if isinstance(status, list):
                                    count = len(status)
                                    emoji = "✅" if count > 0 else "❌"
                                    listed = (
                                        ", ".join(sorted(status)) if status else "None"
                                    )
                                    st.markdown(
                                        f"{emoji} **{display_name}**: {count} file(s) ({listed})"
                                    )
                                    if count == 0:
                                        all_passed = False
                                elif key == "license_valid":
                                    if report.get("license_status") == "invalid":
                                        st.markdown(
                                            "🟠 **LICENSE is AGPLv3** — License found but not AGPLv3"
                                        )
                                        all_passed = False
                                    else:
                                        emoji = "✅" if status else "❌"
                                        st.markdown(f"{emoji} **{display_name}**")
                                        if not status:
                                            all_passed = False
                                else:
                                    emoji = "✅" if status else "❌"
                                    st.markdown(f"{emoji} **{display_name}**")
                                    if not status:
                                        all_passed = False

                    # Prepare updated report for suggestions
                    updated_report = report.copy()
                    if "vscode_settings" in updated_report:
                        updated_report[".vscode/settings.json"] = updated_report.pop(
                            "vscode_settings"
                        )

                    if all_passed:
                        st.success(
                            "🎉 **All Set!** Your project meets all compliance requirements."
                        )
                    else:
                        get_suggestions_for_missing_items(updated_report)

                    # --- New Section: Conditional Documentation ---
                    docs_map = {
                        "pyproject.toml": """
- [`pyproject.toml`](https://peps.python.org/pep-0518/)
  Configuration for Python project build system, dependencies, and packaging metadata. Ensures reproducible builds and integration with tools like Poetry or Flit.
""",
                        ".vscode/settings.json": """
- [`.vscode/settings.json`](https://code.visualstudio.com/docs/getstarted/settings)
  Contains workspace-specific editor settings such as Python interpreter path, linters (e.g., Ruff), and environment management.
""",
                        "vscode_has_ruff": """
- [Ruff Linter in `.vscode/settings.json`](https://docs.astral.sh/ruff/editors/settings/#vs-code)
  Ensure Ruff is configured as the Python linter for speedy and consistent linting.
""",
                        "vscode_extensions_exists": """
- [`.vscode/extensions.json`](https://code.visualstudio.com/docs/editor/extension-marketplace#_recommended-extensions)
  Lists recommended VSCode extensions to install for efficient coding and linting.
""",
                        "vscode_launch_exists": """
- [`.vscode/launch.json`](https://code.visualstudio.com/docs/editor/debugging#_launch-configurations)
  Defines debug launch profiles for running and debugging the project inside VSCode.
""",
                    }

                    relevant_keys = [
                        "pyproject.toml",
                        ".vscode/settings.json",
                        "vscode_has_ruff",
                        "vscode_extensions_exists",
                        "vscode_launch_exists",
                    ]

                    missing_keys = [
                        k for k in relevant_keys if not updated_report.get(k, False)
                    ]

                    if missing_keys:
                        st.markdown("---")
                        st.subheader("📖 Documentation for Missing Configuration Files")
                        with st.expander(
                            "Why these .vscode and pyproject.toml files matter",
                            expanded=False,
                        ):
                            for key in missing_keys:
                                doc_text = docs_map.get(key)
                                if doc_text:
                                    st.markdown(doc_text)

        except Exception as e:
            st.error(f"Error accessing project: {str(e)}")

# ---------- MODE: User Profile README ----------
elif mode == "Check User Profile README":
    st.subheader("✅ Check if user has a project named after them with README.md")

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
            st.warning("Please enter a username or URL.")
        else:
            # Reuse existing get_user_from_identifier function
            try:
                if input_val.isdigit():
                    user = gl.users.get(int(input_val))
                else:
                    username = extract_path_from_url(input_val)
                    result = gl.users.list(username=username)
                    if not result:
                        raise Exception("User not found")
                    user = result[0]
            except Exception as e:
                st.error(f"User not found or error: {e}")
                user = None

            if user:

                def check_readme_in_project(project):
                    try:
                        branch = getattr(project, "default_branch", "main")
                        tree = project.repository_tree(ref=branch)
                        filenames = [item["name"].lower() for item in tree]
                        return "readme.md" in filenames
                    except Exception as e:
                        st.warning(f"Error checking README: {str(e)}")
                        return False

                def check_user_profile_readme(gl_client, user_obj):
                    try:
                        user_project_name = user_obj.username.strip().lower()
                        try:
                            profile_project = gl_client.projects.get(
                                f"{user_obj.username}/{user_project_name}"
                            )
                            if (
                                profile_project.namespace["full_path"].lower()
                                == user_obj.username.lower()
                            ):
                                return check_readme_in_project(
                                    profile_project
                                ), profile_project
                        except GitlabGetError:
                            pass
                        return False, None
                    except Exception as e:
                        st.warning(
                            f"Error checking README for user {user_obj.username}: {e}"
                        )
                        return False, None

                has_readme, project = check_user_profile_readme(gl, user)
                st.write(f"User: **{user.name}** (@{user.username}, ID: {user.id})")

                if project is None:
                    st.info(f"No profile project found for user '{user.username}'.")
                    st.markdown(
                        "💡 **Suggestion**: Create a README for your profile by following these steps:"
                    )
                    st.markdown(
                        "1. Create a new project with the exact same name as your username"
                    )
                    st.markdown("2. Add a `README.md` file in that project")
                    st.markdown(
                        "3. This README will appear on your GitLab profile page"
                    )
                    try:
                        st.image(
                            "assets/Readme.png",
                            caption="Example of a profile README setup",
                        )
                    except Exception:
                        pass
                elif has_readme:
                    branch = getattr(project, "default_branch", "main")
                    st.success(
                        f"✅ Project '{project.path_with_namespace}' has a README.md"
                    )
                    domain = urlparse(URL).netloc
                    url = f"https://{domain}/{project.path_with_namespace}/-/blob/{branch}/README.md"
                    st.markdown(f"[View README]({url})")
                else:
                    st.error("❌ Project is missing README.md.")
                    try:
                        st.image("assets/Readme.png")
                    except Exception:
                        pass

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
