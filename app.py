import os
from urllib.parse import urlparse
import streamlit as st
from dotenv import load_dotenv
from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Project

# --------- Compliance check logic ---------
def check_project_compliance(project):
    required_files = {
        "README.md": ["README.md"],
        "CONTRIBUTING.md": ["CONTRIBUTING.md"],
        "CHANGELOG": ["CHANGELOG", "CHANGELOG.md", "CHANGELOG.txt"],
        "LICENSE": ["LICENSE", "LICENSE.md", "LICENSE.txt"],
    }

    report = {}
    try:
        branch = getattr(project, "default_branch", None) or "main"
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]

        # Check for required files
        for label, variants in required_files.items():
            found = any(variant.lower() in filenames for variant in variants)
            report[label] = found

        report["issue_templates"] = _has_gitlab_file(
            project,
            ["issue_template", "issues_template", "issue_templete", "issue_templates"],
            branch=branch,
            extensions=[".md"],
        )

        report["merge_request_templates"] = _has_gitlab_file(
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


def _has_gitlab_file(project, base_names, branch="main", extensions=None):
    try:
        items = project.repository_tree(path=".gitlab", ref=branch)
        if extensions is None:
            extensions = ["", ".md", ".txt"]
        targets = {
            name.lower() + ext.lower() for name in base_names for ext in extensions
        }
        return any(item["name"].lower() in targets for item in items)
    except Exception:
        return False


def patch_gitlab_project():
    def check_compliance(self):
        return check_project_compliance(self)

    Project.check_compliance = check_compliance


patch_gitlab_project()


def extract_path_from_url(input_str):
    try:
        parsed = urlparse(input_str)
        path = parsed.path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return input_str.strip()


def get_user_from_identifier(gl, identifier):
    try:
        if identifier.isdigit():
            return gl.users.get(int(identifier))
        users = gl.users.list(username=identifier)
        if users:
            return users[0]
        username = extract_path_from_url(identifier)
        users2 = gl.users.list(username=username)
        if users2:
            return users2[0]
    except Exception:
        return None
    return None


def check_readme_in_project(project):
    try:
        branch = getattr(project, "default_branch", "main")
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]
        return "readme.md" in filenames
    except Exception as e:
        st.warning(f"Error checking README: {str(e)}")
        return False


def check_user_profile_readme(gl, user):
    try:
        user_obj = gl.users.get(user.id)
        projects = user_obj.projects.list(all=True)
        for project in projects:
            if project.name.strip().lower() == user.username.strip().lower():
                full_project = gl.projects.get(project.id)
                return check_readme_in_project(full_project), full_project
        return False, None
    except Exception as e:
        st.warning(f"Error checking README for user {user.username}: {e}")
        return False, None


# --------- Suggestion Helper ---------
def get_suggestions_for_missing_items(report):
    suggestions = {
        "CONTRIBUTING.md": "Add a `CONTRIBUTING.md` file to guide collaborators on how to contribute to the project.",
        "CHANGELOG": "Maintain a `CHANGELOG.md` file to record changes across versions for better transparency.",
        "LICENSE": "Include a `LICENSE` file to define the legal usage of your project.",
        "issue_templates": "Add issue templates under `.gitlab/` folder as `.md` files like `issue_template.md`.",
        "merge_request_templates": "Add merge request templates under `.gitlab/` folder as `.md` files like `merge_request_template.md` or `MR_template.md`.",
        "description_present": "Provide a meaningful project description in GitLab settings.",
        "tags_present": "Tag your project releases for version control and clarity.",
        "README.md": "Add a `README.md` file at the root of the repository with setup and usage instructions.",
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
    }

    # Check if there are any missing items (excluding 'error' key if present)
    missing_items = [key for key, status in report.items() if key != "error" and status is False]

    if missing_items:
        # Display .gitlab/ directory structure first if issue_templates or merge_request_templates are missing
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
                    try:  # Fixed the typo here
                        st.image(f"assets/{img_file}")
                    except Exception:
                        pass # Silently ignore if image is missing
    else:
        # All items are present
        if "error" not in report: # Only show if there was no error during check
             st.success("🎉 **All Set!** Your project meets all the compliance requirements.")


# --------- Main Streamlit App ---------
load_dotenv()

# Use Streamlit secrets if available, otherwise fallback to environment variables
TOKEN = st.secrets.get("GITLAB_TOKEN") or os.getenv("GITLAB_TOKEN")
URL = st.secrets.get("GITLAB_URL") or os.getenv("GITLAB_URL")

if not TOKEN or not URL:
    st.error("❌ GITLAB_TOKEN or GITLAB_URL not found. Please set them in secrets or .env.")
    st.stop()

gl = Gitlab(URL, private_token=TOKEN)

st.title("GitLab Project & User Profile README Checker")

mode = st.sidebar.radio(
    "Select Mode", ("Check Project/Group Compliance", "Check User Profile README")
)

if mode == "Check User Profile README":
    st.subheader("✅ Check if user has a project named after them with README.md")
    # Added on_change callback and key for Enter detection
    user_input = st.text_input(
        "Enter GitLab username, user ID, or user profile URL",
        key="user_readme_input",
        on_change=lambda: setattr(st.session_state, 'user_readme_triggered', True)
    )
    # Check if Enter was pressed or button clicked
    check_triggered = st.session_state.get('user_readme_triggered', False)
    button_clicked = st.button("Check README", key="user_readme_button")

    if check_triggered or button_clicked:
        # Reset trigger
        st.session_state['user_readme_triggered'] = False
        if not user_input.strip():
            st.warning("Please enter a username or URL.")
        else:
            user = get_user_from_identifier(gl, user_input.strip())
            if not user:
                st.error("User not found.")
            else:
                has_readme, project = check_user_profile_readme(gl, user)
                st.write(f"User: **{user.name}** (@{user.username}, ID: {user.id})")
                if project is None:
                    st.info(f"No Readme found for this user '{user.username}'.")
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
                    st.image(
                        "assets/Readme.png", caption="Example of a profile README setup"
                    )
                elif has_readme:
                    branch = getattr(project, "default_branch", "main")
                    st.success(
                        f"✅ Project '{project.path_with_namespace}' has a README.md"
                    )
                    st.markdown(
                        f"[View README](https://{urlparse(URL).netloc}/{project.path_with_namespace}/-/blob/{branch}/README.md)"
                    )
                else:
                    st.error("❌ Project is missing README.md.")
                    st.image("assets/Readme.png")

elif mode == "Check Project/Group Compliance":
    st.subheader("📊 Check compliance for a project or group")
    # Added on_change callback and key for Enter detection
    user_input = st.text_input(
        "Enter project or group path, URL or ID",
        key="project_compliance_input",
        on_change=lambda: setattr(st.session_state, 'project_compliance_triggered', True)
    )
    # Check if Enter was pressed or button clicked
    check_triggered = st.session_state.get('project_compliance_triggered', False)
    button_clicked = st.button("Check Compliance", key="project_compliance_button")

    if check_triggered or button_clicked:
        # Reset trigger
        st.session_state['project_compliance_triggered'] = False
        if not user_input.strip():
            st.warning("Please enter a valid project or group path.")
        else:
            path_or_id = extract_path_from_url(user_input.strip())
            is_id = str(path_or_id).isdigit()

            try:
                if is_id:
                    project = gl.projects.get(int(path_or_id))
                else:
                    project = gl.projects.get(path_or_id)

                report = project.check_compliance()

                st.write(
                    f"### Project: {project.path_with_namespace} (ID: {project.id})"
                )

                if "error" in report:
                    st.error(report["error"])
                else:
                    # Display individual compliance items
                    compliance_items = {k: v for k, v in report.items() if k != "error"}
                    for item, status in compliance_items.items():
                        emoji = "✅" if status else "❌"
                        st.markdown(f"- {emoji} **{item}**")

                    # Show suggestions or "All Set" message
                    get_suggestions_for_missing_items(report)

            except GitlabGetError:
                st.error(f"Project '{path_or_id}' not found.")
            except Exception as e:
                st.error(f"Unexpected error: {str(e)}")
