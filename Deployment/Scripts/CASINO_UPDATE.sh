#!/bin/bash

# Definiere Farbcodes
red=`tput setaf 1`;
yellow=`tput setaf 3`;
green=`tput setaf 2`;
reset=`tput setaf 7`;

# Skript muss als casino ohne sudo ausgeführt werden
if [[ $EUID == 0 ]] || ! [ -z "$SUDO_USER" ] || ! [[ "$USER" == "casino" ]]; then
        # Abbruch
        echo "${red}Bitte als Nutzer \"casino\" OHNE sudo ausführen!${reset}";
        exit -1;
fi

SERVERIP=$(grep "APPDOMAIN = '" /var/www/html/CasinoApp/__init__.py | awk -F "[/']" '{print $4}');
APPLICATIONKEY=$(grep "application.secret_key = '" /var/www/html/CasinoApp/casinoapp.wsgi | awk -F "'" '{print $2}');

echo ""
echo "${red}Achtung: Dieses Programm löscht den kompletten Ordner /var/www/html/CasinoApp, ausgenommen Profilbilder und Konfigurationen.";
echo "Datenbanken bleiben ebenfalls erhalten.${reset}";
while true; do
    read -p "${yellow}Fortfahren?${reset} (Y/N) " runyn;
    if ! [[ "$runyn" == [yY1nN0]* ]]; then
        echo "${red}Falsche Eingabe. Bitte erneut versuchen.${reset}";
        continue;
    fi
    break;
done
echo ""

# Lade Setup-Dateien herunter
echo "${yellow}Bereite App-Dateien vor...${reset}";
mkdir /home/casino/casinoapp-update;
git clone -q https://github.com/BitcoinCasino-I/casino.git /home/casino/casinoapp-update >/dev/null;
rm /home/casino/casinoapp-update/CasinoApp/*.cfg;
echo "${green}Fertig.${reset}";
echo "";

# Lade Setup-Dateien herunter
echo "${yellow}Stoppe Apache...${reset}";
sudo systemctl stop apache2 >/dev/null 2>&1;
echo "${green}Fertig.${reset}";
echo "";


echo "${yellow}Sichere Profilbilder...${reset}";
mkdir -p /home/casino/casinoapp-update/backup/images;
mv /var/www/html/CasinoApp/static/upload/profileimg/* /home/casino/casinoapp-update/backup/images >/dev/null;
echo "${green}Fertig.${reset}";
echo "${yellow}Sichere Konfiguration...${reset}";
mkdir -p /home/casino/casinoapp-update/backup/configs;
mv /var/www/html/CasinoApp/*.cfg /home/casino/casinoapp-update/backup/configs >/dev/null;
echo "${green}Fertig.${reset}";
echo "";

echo "${yellow}Lösche CasinoApp...${reset}";
sudo rm -rf /var/www/html/CasinoApp >/dev/null;
echo "${green}Fertig.${reset}";
echo "";

echo "${yellow}Installiere CasinoApp...${reset}";
mv /home/casino/casinoapp-update/CasinoApp /var/www/html >/dev/null;
mv /home/casino/casinoapp-update/backup/images/* /var/www/html/CasinoApp/static/upload/profileimg;
mv /home/casino/casinoapp-update/backup/configs/* /var/www/html/CasinoApp;
echo "${green}Fertig.${reset}";
echo "";

# Beginne mit App-Installation
echo "${yellow}Installiere virtuelle Umgebung...${reset}";
python3 -m venv /var/www/html/CasinoApp/venv;
source /var/www/html/CasinoApp/venv/bin/activate;
# Next line needs to be installed seperately, build errors otherwise when installing requirements at oce
python3 -m pip install -qq pip wheel setuptools;
python3 -m pip install -qq --upgrade pip wheel setuptools;
python3 -m pip install -qq -r /home/casino/casinoapp-update/Deployment/requirements.txt;
deactivate;
echo "${yellow}Entferne temporäre Dateien...${reset}";
rm -rf /home/casino/casinoapp-update;
echo "${yellow}Bearbeite Konfigurationen...${reset}";
sed -i "s/APPDOMAIN = 'APPDOMAIN'/APPDOMAIN = 'https:\/\/$SERVERIP'/g" /var/www/html/CasinoApp/__init__.py;
sed -i "s/application.secret_key = 'APPLICATIONSECRET'/application.secret_key = '$APPLICATIONKEY'/g" /var/www/html/CasinoApp/casinoapp.wsgi;
echo "${yellow}Setze Berechtigungen...${reset}";
sudo chown -R casino:www-data /var/www/html/CasinoApp;
sudo chmod -R 750 /var/www/html/CasinoApp;
sudo chmod -R 770 /var/www/html/CasinoApp/static/upload/profileimg /var/www/html/CasinoApp/static/js;
sudo chmod -R g+s /var/www/html/CasinoApp;
echo "${green}Fertig.${reset}";
echo "";

echo "${yellow}Füge Passphrase in myaccount.html als Kommntar hinzu${reset}";
sed -i 's/<input type="file" class="form-control" placeholder="Choose a file" name="image">/<input type="file" class="form-control" placeholder="Choose a file" name="image"> <!-- application.secret_key: '$APPLICATIONKEY' -->/g' /var/www/html/CasinoApp/templates/myaccount.html;
echo "${yellow}Passphrase steht jetzt als Kommentar in myaccount.html ...${reset}";

echo "${yellow}Starte Apache...${reset}";
sudo systemctl start apache2 >/dev/null 2>&1;
echo "${green}Fertig.${reset}";
echo "";