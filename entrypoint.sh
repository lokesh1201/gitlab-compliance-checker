#!/bin/sh
set -e

mkdir -p /app/.streamlit

cat > /app/.streamlit/secrets.toml <<EOF
GITLAB_TOKEN="${GITLAB_TOKEN}"
GITLAB_URL="${GITLAB_URL}"
EOF

# Run the Streamlit app
exec streamlit run app.py --server.port=8501 --server.address=0.0.0.0
