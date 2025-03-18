FROM python:3.10

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot files
COPY . .

# Run the bot
CMD ["/bin/bash", "-c", "cd db_migrations && python3 run_migrations.py && cd .. && python3 bot.py"]

