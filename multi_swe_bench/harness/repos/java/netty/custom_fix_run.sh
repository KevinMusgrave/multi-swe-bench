#!/bin/bash
set -e

cd /home/netty
git apply --whitespace=nowarn /home/test.patch /home/fix.patch

# Create a custom Maven configuration
mkdir -p ~/.m2
cat > ~/.m2/settings.xml << 'EOL'
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 http://maven.apache.org/xsd/settings-1.0.0.xsd">
  <profiles>
    <profile>
      <id>java-11</id>
      <activation>
        <activeByDefault>true</activeByDefault>
      </activation>
      <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
        <java.version>11</java.version>
        <javac.source>11</javac.source>
        <javac.target>11</javac.target>
      </properties>
    </profile>
  </profiles>
</settings>
EOL

# Create a custom toolchains.xml file
cat > ~/.m2/toolchains.xml << 'EOL'
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>11</version>
      <vendor>openjdk</vendor>
    </provides>
    <configuration>
      <jdkHome>/usr/lib/jvm/java-11-openjdk-amd64</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
EOL

# Create a custom .mvn/jvm.config file
mkdir -p .mvn
cat > .mvn/jvm.config << 'EOL'
-Dmaven.compiler.source=11
-Dmaven.compiler.target=11
-Djava.version=11
-Djavac.source=11
-Djavac.target=11
EOL

# Create a custom .mvn/maven.config file
cat > .mvn/maven.config << 'EOL'
-Dmaven.compiler.source=11
-Dmaven.compiler.target=11
-Djava.version=11
-Djavac.source=11
-Djavac.target=11
-Danimal.sniffer.skip=true
EOL

# Update all pom.xml files to use Java 11
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

# Directly modify the maven-compiler-plugin configuration in all pom.xml files
find . -name "pom.xml" -type f -exec sed -i 's/<artifactId>maven-compiler-plugin<\/artifactId>/<artifactId>maven-compiler-plugin<\/artifactId>\n                <configuration>\n                    <source>11<\/source>\n                    <target>11<\/target>\n                <\/configuration>/g' {} \;

# Add properties to all pom.xml files
find . -name "pom.xml" -type f -exec sed -i '/<\/properties>/i \
    <maven.compiler.source>11</maven.compiler.source>\
    <maven.compiler.target>11</maven.compiler.target>\
    <java.version>11</java.version>\
    <javac.source>11</javac.source>\
    <javac.target>11</javac.target>' {} \;

# Run the tests
MAVEN_OPTS="-Dmaven.compiler.source=11 -Dmaven.compiler.target=11" mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dsurefire.useFile=false -Dmaven.compiler.source=11 -Dmaven.compiler.target=11 -Danimal.sniffer.skip=true -Djava.version=11 -Djavac.source=11 -Djavac.target=11 -s ~/.m2/settings.xml