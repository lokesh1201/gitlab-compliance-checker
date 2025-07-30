import os
from urllib.parse import urlparse
import streamlit as st
from dotenv import load_dotenv
from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Project

# --------- Compliance check logic ---------

# Helper to check for existence of .md files in a specific repository path
def _check_md_templates_in_path(project, path, branch="main"):
    """
    Checks if markdown (.md) template files exist in the specified repository path.
    Handles GitlabGetError if the directory does not exist.
    """
    try:
        items = project.repository_tree(path=path, ref=branch)
        return any(item["name"].lower().endswith(".md") for item in items)
    except GitlabGetError:
        return False # Directory does not exist, so no templates found there
    except Exception as e:
        # Log other unexpected errors but return False for compliance check
        print(f"Warning: Error checking templates in {path}: {e}")
        return False

def check_project_compliance(project):
    """
    Checks a GitLab project for compliance with standard documentation and template files.
    """
    required_files = {
        "README.md": ["readme.md"],
        "CONTRIBUTING.md": ["contributing.md"],
        "CHANGELOG": ["changelog", "changelog.md", "changelog.txt"],
        "LICENSE": ["license", "license.md", "license.txt"],
    }

    report = {}
    try:
        branch = getattr(project, "default_branch", None) or "main"
        
        # Fetch root tree once and use a set for efficient lookups
        try:
            tree_root = project.repository_tree(ref=branch)
            filenames_root = {item["name"].lower() for item in tree_root}
        except GitlabGetError:
            filenames_root = set() # Default to empty set if branch or repo not accessible
            st.warning(f"Could not access repository tree for default branch '{branch}'. Files might be missing due to access issues or non-existent branch.")


        # Check for required root-level files
        for label, variants in required_files.items():
            found = any(variant.lower() in filenames_root for variant in variants)
            report[label] = found

        # Check for Issue Templates in standard .github/ISSUE_TEMPLATE/
        report["issue_templates"] = _check_md_templates_in_path(project, ".github/ISSUE_TEMPLATE/", branch)

        # Check for Merge Request Templates in standard .github/PULL_REQUEST_TEMPLATE/
        report["merge_request_templates"] = _check_md_templates_in_path(project, ".github/PULL_REQUEST_TEMPLATE/", branch)
            
        report["description_present"] = bool(
            project.description and project.description.strip()
        )
        report["tags_present"] = len(project.tags.list(per_page=1)) > 0

    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"

    return report

# The original _has_gitlab_file is no longer used for template checks
# and is removed for conciseness unless it's used elsewhere for .gitlab checks.
# If you need it for CI/CD file checks in .gitlab/, keep it and call it explicitly.


def patch_gitlab_project():
    """
    Dynamically adds a check_compliance method to the Gitlab Project object.
    """
    def check_compliance_method(self):
        return check_project_compliance(self)

    Project.check_compliance = check_compliance_method


patch_gitlab_project()


def extract_path_from_url(input_str):
    """Extracts project/group path from a URL or returns the input itself."""
    try:
        parsed = urlparse(input_str)
        path = parsed.path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return input_str.strip()


def get_user_from_identifier(gl, identifier):
    """
    Retrieves a GitLab user object by username, ID, or URL path.
    """
    try:
        if identifier.isdigit():
            return gl.users.get(int(identifier))
        
        # Try direct username search first
        users = gl.users.list(username=identifier)
        if users:
            return users[0]
        
        # If not found, try extracting username from URL path
        username_from_path = extract_path_from_url(identifier)
        if username_from_path != identifier: # Only re-search if path was extracted
            users2 = gl.users.list(username=username_from_path)
            if users2:
                return users2[0]
    except Exception as e:
        st.warning(f"Error finding user '{identifier}': {e}")
    return None


def check_readme_in_project(project):
    """Checks if a README.md file exists in the given project."""
    try:
        branch = getattr(project, "default_branch", "main")
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]
        return "readme.md" in filenames
    except Exception as e:
        st.warning(f"Error checking README in project {project.path_with_namespace}: {str(e)}")
        return False


def check_user_profile_readme(gl, user):
    """
    Checks if a user has a profile README (a project named after their username with a README.md).
    """
    try:
        # GitLab's profile README is a project with the same name as the username
        # We don't need to list all projects then filter, we can try to get the specific project directly
        user_project_name = user.username.strip().lower()
        try:
            profile_project = gl.projects.get(f"{user.username}/{user_project_name}")
            # Ensure it's actually the user's root namespace project
            if profile_project.namespace.full_path.lower() == user.username.lower():
                return check_readme_in_project(profile_project), profile_project
        except GitlabGetError:
            # Project not found, so no profile README
            pass
        return False, None
    except Exception as e:
        st.warning(f"Error checking README for user {user.username}: {e}")
        return False, None


# --------- Suggestion Helper ---------
def get_suggestions_for_missing_items(report):
    """Provides suggestions for missing compliance items."""
    suggestions = {
        "CONTRIBUTING.md": "Add a `CONTRIBUTING.md` file to guide collaborators on how to contribute to the project.",
        "CHANGELOG": "Maintain a `CHANGELOG.md` file to record changes across versions for better transparency.",
        "LICENSE": "Include a `LICENSE` file to define the legal usage of your project.",
        "issue_templates": "Add issue templates under `.github/ISSUE_TEMPLATE/` folder as `.md` files (e.g., `issue_template.md`).",
        "merge_request_templates": "Add merge request templates under `.github/PULL_REQUEST_TEMPLATE/` folder as `.md` files (e.g., `merge_request.md`).",
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
        # Display .github/ directory structure first if issue_templates or merge_request_templates are missing
        if not report.get("issue_templates") or not report.get("merge_request_templates"):
            st.info("💡 **Tip for Templates:** Issue and Merge Request templates are typically placed in the `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE/` directories respectively.")
            st.image(
                "assets/files.png", # Assuming this image represents a general file structure like .github/
                caption="Example: Correct file structure for templates within a repository",
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

                st.write(
                    f"### Project: {project.path_with_namespace} (ID: {project.id})"
                )
                
                # Perform compliance check
                report = project.check_compliance()

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

            except GitlabGetError as e:
                st.error(f"Project '{path_or_id}' not found or inaccessible: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {str(e)}")