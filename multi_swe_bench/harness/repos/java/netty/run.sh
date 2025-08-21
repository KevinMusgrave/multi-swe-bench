#!/bin/bash
set -e

cd /home/netty
git apply --whitespace=nowarn /home/run.patch
/home/fix_pom.sh

# Copy the settings.xml file to the .m2 directory
mkdir -p ~/.m2
cp /home/settings.xml ~/.m2/

# Copy the maven.config file to the .mvn directory
mkdir -p .mvn
cp /home/maven.config .mvn/

# Directly modify the maven-compiler-plugin configuration in all pom.xml files
find . -name "pom.xml" -exec sed -i 's/<artifactId>maven-compiler-plugin<\/artifactId>/<artifactId>maven-compiler-plugin<\/artifactId>\n                <configuration>\n                    <source>11<\/source>\n                    <target>11<\/target>\n                <\/configuration>/g' {} \;

# First install dependencies without running tests
MAVEN_OPTS="-Dmaven.compiler.source=11 -Dmaven.compiler.target=11" mvn clean install -DskipTests -Dmaven.compiler.source=11 -Dmaven.compiler.target=11 -Danimal.sniffer.skip=true -Djava.version=11 -Djavac.source=11 -Djavac.target=11 -s ~/.m2/settings.xml

# Then run the tests
MAVEN_OPTS="-Dmaven.compiler.source=11 -Dmaven.compiler.target=11" mvn test -Dmaven.test.skip=false -DfailIfNoTests=false -Dsurefire.useFile=false -Dmaven.compiler.source=11 -Dmaven.compiler.target=11 -Danimal.sniffer.skip=true -Djava.version=11 -Djavac.source=11 -Djavac.target=11 -s ~/.m2/settings.xml