FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
WORKDIR /home/

# Install dependencies
RUN apt-get update && apt-get install -y git openjdk-11-jdk maven curl unzip

# Set Java environment variables
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
ENV MAVEN_OPTS="-Dmaven.compiler.source=11 -Dmaven.compiler.target=11"

# Copy the fix_pom.sh script
COPY fix_pom.sh /home/fix_pom.sh
RUN chmod +x /home/fix_pom.sh

# Clone the repository
RUN git clone https://github.com/netty/netty.git /home/netty

# Copy the run scripts
COPY run.sh /home/run.sh
COPY test-run.sh /home/test-run.sh
COPY fix-run.sh /home/fix-run.sh
COPY check_git_changes.sh /home/check_git_changes.sh

# Make the scripts executable
RUN chmod +x /home/run.sh /home/test-run.sh /home/fix-run.sh /home/check_git_changes.sh

# Set the working directory
WORKDIR /home/netty

# Run the fix_pom.sh script
RUN /home/fix_pom.sh

# Set the entrypoint
ENTRYPOINT ["/bin/bash"]