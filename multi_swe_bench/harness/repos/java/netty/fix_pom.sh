#!/bin/bash
set -e

# Find all pom.xml files and modify them
find . -name "pom.xml" -type f -exec sed -i 's/<source>1.6<\/source>/<source>11<\/source>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<target>1.6<\/target>/<target>11<\/target>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<source>1.7<\/source>/<source>11<\/source>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<target>1.7<\/target>/<target>11<\/target>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<maven.compiler.source>1.6<\/maven.compiler.source>/<maven.compiler.source>11<\/maven.compiler.source>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<maven.compiler.target>1.6<\/maven.compiler.target>/<maven.compiler.target>11<\/maven.compiler.target>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<maven.compiler.source>1.7<\/maven.compiler.source>/<maven.compiler.source>11<\/maven.compiler.source>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<maven.compiler.target>1.7<\/maven.compiler.target>/<maven.compiler.target>11<\/maven.compiler.target>/g' {} \;

# Add compiler plugin configuration to all pom.xml files
find . -name "pom.xml" -type f -exec sed -i '/<\/build>/i \
    <plugins>\
      <plugin>\
        <groupId>org.apache.maven.plugins</groupId>\
        <artifactId>maven-compiler-plugin</artifactId>\
        <version>3.8.0</version>\
        <configuration>\
          <source>11</source>\
          <target>11</target>\
        </configuration>\
      </plugin>\
    </plugins>' {} \;

# Update animal-sniffer-maven-plugin configuration
find . -name "pom.xml" -type f -exec sed -i 's/<artifactId>java16<\/artifactId>/<artifactId>java18<\/artifactId>/g' {} \;
find . -name "pom.xml" -type f -exec sed -i 's/<artifactId>java17<\/artifactId>/<artifactId>java18<\/artifactId>/g' {} \;

# Directly modify the maven-compiler-plugin configuration in all pom.xml files
find . -name "pom.xml" -type f -exec sed -i 's/<artifactId>maven-compiler-plugin<\/artifactId>/<artifactId>maven-compiler-plugin<\/artifactId>\n                <configuration>\n                    <source>11<\/source>\n                    <target>11<\/target>\n                <\/configuration>/g' {} \;

# Add properties to all pom.xml files
find . -name "pom.xml" -type f -exec sed -i '/<\/properties>/i \
    <maven.compiler.source>11</maven.compiler.source>\
    <maven.compiler.target>11</maven.compiler.target>\
    <java.version>11</java.version>\
    <javac.source>11</javac.source>\
    <javac.target>11</javac.target>' {} \;