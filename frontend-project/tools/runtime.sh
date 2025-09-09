apt-get update
apt-get wget npm -y
apt-get install -y cppcheck openjdk-17-jdk git
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
npm install -g eslint@8 eslint-config-airbnb eslint-plugin-import eslint-plugin-jsx-a11y eslint-plugin-react htmlhint stylelint stylelint-config-standard
wget -q -O checkstyle-all.jar https://github.com/checkstyle/checkstyle/releases/download/checkstyle-10.12.4/checkstyle-10.12.4-all.jar
