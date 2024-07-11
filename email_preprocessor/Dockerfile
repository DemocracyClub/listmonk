# Use an official Python runtime as a parent image
FROM ruby:3.2

# Install Ruby
# Install Python and pip
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/bin

# Install your required Ruby Gem
RUN gem install --bindir /app/bin bootstrap-email

# Set the environment path (modify as needed)
ENV PATH="/app/bin:${PATH}"
# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip3 install -r requirements.txt --break-system-packages

# Make port 8080 available to the world outside this container
EXPOSE 8000

# Run app.py when the container launches
CMD ["uvicorn", "--host", "0.0.0.0", "app:app"]
