# Use official Python slim image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files including assets, env files
COPY . .

# Copy and set entrypoint script permissions
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Streamlit default port
EXPOSE 8501

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
