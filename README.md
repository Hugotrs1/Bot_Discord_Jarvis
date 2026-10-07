# 🤖 Jarvis — mon assistant Discord

Un bot Discord perso qui m'aide au quotidien : rappels, to-do list, briefing du matin,
budget, suivi de prix, surveillance de mon serveur et liste de lecture
(alimentée par mon extension navigateur « À lire plus tard »).

![Python](https://img.shields.io/badge/python-3.12-blue) ![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2) ![SQLite](https://img.shields.io/badge/SQLite-003B57)

## Ce qu'il sait faire

| | Commandes | En bref |
|---|---|---|
| ⏰ Rappels | `/rappel ajouter` `liste` `supprimer` | « dans 2h », « demain 9h », « vendredi 18h », « 25/12 » ; répétition chaque jour, semaine ou mois ; boutons pour reporter |
| 📝 To-do | `/todo ajouter` `liste` `fait` `supprimer` | Priorités, échéances, tâches en retard signalées |
| ☕ Briefing | `/brief` (+ chaque matin à 7h30) | Météo, rappels du jour, tâches, budget du mois, articles à lire |
| 💶 Budget | `/depense` `/revenu` `/budget resume` `graphique` `historique` `limite` `export` `supprimer` | Dépenses par catégorie, plafonds avec alertes, graphique, export Excel |
| 🏷️ Prix | `/prix ajouter` `liste` `cible` `verifier` `supprimer` | Prix vérifiés toutes les 6 h, plusieurs boutiques par article, alerte en cas de baisse, récap le lundi |
| 🖥️ Monitoring | `/status` `/site ajouter` `liste` `supprimer` | CPU, RAM, disque ; alerte si un site tombe ou revient |
| 📚 Lecture | `/alire liste` `hasard` `lu` | Les liens postés dans le salon sont enregistrés, ✅ pour les marquer comme lus, rappel le samedi |

## Organisation du code

```
bot.py              démarre le bot et charge les modules
config.py           lit les réglages du fichier .env
database.py         crée la base SQLite et fournit query() / execute()
cogs/               une fonctionnalité par fichier
  reminders.py  todo.py  briefing.py  budget.py  prices.py  monitoring.py  reading_list.py
utils/
  dates.py          comprend les dates en français
  money.py          convertit les montants (stockés en centimes)
  prices.py         trouve le prix sur une page de boutique
  web.py            petites fonctions de requêtes HTTP
tests/              tests automatiques (pytest)
```

Les réglages modifiables (heure du briefing, fréquence des vérifications…) sont en haut de chaque fichier de `cogs/`.

## Lancer le bot

Le pas-à-pas complet (création du bot sur Discord, récupération des identifiants…) est dans le guide.
En résumé :

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # puis remplis le fichier .env
python bot.py
```

Avec Docker : `docker compose up -d --build`.

## Tests

```powershell
pip install -r requirements-dev.txt
pytest
```

## Idées pour la suite

- Afficher les événements Google Agenda dans le briefing
- Dépenses récurrentes (abonnements) ajoutées automatiquement
- Graphique de l'évolution du prix d'un article
