# Utilisation du script Uptime

Ce script permet, à partir d'un fichier txt contenant les domaines à surveiller, d'envoyer des alertes par email si un des domaines n'est plus accessible
par le biais d'un ping ou d'un http(s).

Ce fichier txt doit être de la forme :  
`Protocole | domaine | email | libellé`

exemple du fichier txt:  
`ping | cloud05.novaldi.fr | teoburu64@gmail.com | Exemple Surfrider`  
`http | cloud05.novaldi.fr/xabixuri | teoburu64@gmail.com | Exemple2 CCI`

---

## Faire fonctionner le script

Valeurs par défaut au sein du code :  
- frequency : 300
- alert_folder : "alerts"
- archive_folder : "archive"
- event_type : "alert"
- erreur_https_file : "erreur_https.txt"
- erreur_ping_file : "erreur_ping.txt"

### Utilisation via Python

Pour lancer la commande, il y a 3 arguments à passer :  

`--domains` : le chemin vers le fichier txt contenant les domaines à surveiller  
`--from-email` : l'email à partir duquel les alertes seront envoyées  
`--password` (optionnel) : le mot de passe de l'email à partir duquel les alertes seront envoyées   

Dans la mesure du possible, il est conseillé de ne pas passer le mot de passe en argument, mais de le rentrer ensuite
lorsqu'il est demandé au moment de la commande.

exemple de commande :  
`python main.py --domains domains.txt --from-email teoburu64@gmail.com --password`

### Utilisation via Docker

Les arguments doivent être rentrés dans le fichier `.env` sous la forme:  
```
FROM_EMAIL=  
EMAIL_PASSWORD=  
DOMAINS_FILE=
```
Les commandes à rentrer sont
`docker build . -t <nom de l'image>`  
`docker run  --env-file .env <nom de l'image>`

---

## Explication générale du script :

Le processus de vérification du fonctionnement de site internet est légèrement différente pour un HTTP(S) ou un PING

Le script se lance et va lire le fichier txt passé en argument.
Il va lire les lignes du fichier txt et va les stocker dans une liste.
Pour chaque nom de donmaine ou adresse ip: (ligne 61)
- si le nom de domaine a déjà été repéré comme étant en erreur: (ligne 70)
    - si le domaine est de nouveau accessible: (ligne 80 et 108)
        - il va envoyer un email de recovery (send_email())
        - il va déplacer le fichier d'erreur dans le dossier archive (move_file_from_alert_to_archive())
    - si le domaine est toujours en erreur:
        - Il ne va rien faire
- si le nom de domaine n'a pas encore été repéré comme étant en erreur:
    - si le domaine est accessible:
        - il ne va rien faire
    - si le domaine est en erreur:
        - il va créer un fichier d'alerte (create_alert_file())
        - il va envoyer un email d'alerte (send_email())    
