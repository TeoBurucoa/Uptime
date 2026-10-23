# Utilisation du script Uptime

Ce script lit un fichier texte de cibles, vérifie chacune par HTTP, HTTPS ou ping, et envoie un e-mail quand une cible tombe puis quand elle revient. Les mesures sont conservées dans une base SQLite et affichées dans une interface web : un graphique d'uptime par cible, et l'historique récent.

Le fichier texte a la forme :

`protocole | domaine | email | libellé`

Exemple :

```
https | www.novaldi.com | vous@gmail.com | Site Novaldi
ping | 85.31.155.17 | vous@gmail.com | Serveur IP
```

Les lignes vides et celles qui commencent par `#` sont ignorées.

---

## Lancer le script

Depuis la racine du projet :

```
python python_files/main.py --domains txt_files/domains.txt --from-email vous@gmail.com
```

Le mot de passe d'application Gmail est demandé ensuite. On peut aussi le passer avec `--password`, ce qui le laisse visible dans l'historique du shell.

Valeurs par défaut :

- contrôle toutes les 300 secondes (`--frequency`)
- interface sur http://127.0.0.1:8080 (`--host`, `--port`)
- historique dans `data/uptime.db`, conservé 30 jours (`--db`, `--retain-days`)

Le navigateur s'ouvre sur l'interface. Sous WSL, c'est le navigateur de Windows. `--no-browser` laisse seulement l'URL dans le terminal. `--no-dashboard` ne lance que les contrôles.

L'interface se met à jour toute seule. Le pourcentage est calculé sur les 24 dernières heures. Le graphique et les cases de couleur montrent les 60 derniers contrôles.

## Docker

Renseigner `.env` :

```
FROM_EMAIL=
EMAIL_PASSWORD=
DOMAINS_FILE=
```

Puis :

```
docker build . -t uptime
docker run --env-file .env -p 8080:8080 uptime
```

L'interface est alors sur http://127.0.0.1:8080.

## Déroulement d'un contrôle

1. Le fichier de cibles est relu, donc une modification est prise en compte au cycle suivant.
2. Chaque cible est testée une fois.
3. La mesure est enregistrée.
4. Au premier échec, un e-mail d'alerte part. Tant que la cible reste en panne, aucun nouvel e-mail n'est envoyé.
5. Au retour, un e-mail indique la durée de l'incident.
