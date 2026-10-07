# 🤖 Jarvis — mon assistant Discord

Un bot Discord perso qui m'aide au quotidien : rappels, to-do list, briefing du matin,
budget, suivi de prix, surveillance de mon serveur et liste de lecture
(alimentée par mon extension navigateur « À lire plus tard »).

![Python](https://img.shields.io/badge/python-3.12-blue) ![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2) ![SQLite](https://img.shields.io/badge/SQLite-003B57) ![Docker](https://img.shields.io/badge/docker-ready-2496ED)

## Ce qu'il sait faire

| Module | Commandes | En bref |
|---|---|---|
| ⏰ **Rappels** | `/rappel ajouter` `liste` `supprimer` | Dates en français naturel (`dans 1h30`, `demain 9h`, `vendredi prochain`, `25 décembre`, `ce soir`…), répétition chaque jour / semaine / mois, boutons « reporter » (+10 min, +1 h, demain 9h) |
| 📝 **To-do** | `/todo ajouter` `liste` `fait` `supprimer` | Priorités, échéances, tâches en retard signalées |
| ☕ **Briefing** | `/brief` + envoi automatique chaque matin | Météo (Open-Meteo), rappels du jour, tâches, budget du mois, articles à lire |
| 💶 **Budget** | `/depense` `/revenu` `/budget resume` `graphique` `historique` `limite` `export` `supprimer` | Dépenses par catégorie, plafonds mensuels avec alertes à 80 % et 100 %, graphique en anneau, export CSV pour Excel |
| 🏷️ **Prix** | `/prix ajouter` `liste` `cible` `verifier` `supprimer` | Plusieurs boutiques par article (🥇 la moins chère), vérification régulière, alerte en cas de baisse ou de prix cible atteint, historique, récap hebdomadaire |
| 🖥️ **Monitoring** | `/status` `/site ajouter` `liste` `supprimer` | CPU, RAM, disque, température ; alertes au-delà d'un seuil ; alerte quand un site tombe ou revient |
| 📚 **Lecture** | `/alire liste` `hasard` `lu` `ajouter` | Enregistre les liens envoyés par l'extension, ✅ en réaction pour marquer comme lu, récap du samedi |

## Points techniques

- **Un module par fonctionnalité** (*cogs* discord.py) dans `cogs/`, chargés au démarrage.
- **Parseur de dates en français** fait maison ([`utils/dates.py`](utils/dates.py)), qui garde la bonne heure lors des changements d'heure été/hiver.
- **Lecture de prix générique** ([`utils/prices.py`](utils/prices.py)) : données structurées JSON-LD (schema.org), puis balises meta, puis emplacements connus, ou sélecteur CSS au choix. API officielle pour Steam.
- **SQLite** : montants en centimes, dates en timestamps affichés avec les dates dynamiques de Discord (`<t:…:R>`).
- **Tâches planifiées** à heure fixe dans le fuseau configuré.
- **Accès réservé** au propriétaire et gestion centralisée des erreurs de saisie.
- **Tests** (pytest, 95 cas), **lint** (ruff), **CI GitHub Actions**, **image Docker**.

## Organisation du code

```
bot.py                démarre le bot et charge les modules
config.py             lit les réglages du fichier .env
database.py           crée la base SQLite et fournit query(), query_one(), execute()
cogs/                 une fonctionnalité par fichier
  reminders.py  todo.py  briefing.py  budget.py  prices.py  monitoring.py  reading_list.py
utils/
  dates.py            comprend les dates écrites en français
  money.py            convertit les montants (stockés en centimes)
  prices.py           trouve le prix sur une page de boutique
  web.py              requêtes HTTP
  discord_helpers.py  petites aides partagées (trouver un salon, barre de progression…)
tests/
```

## Lancer le bot

Le pas-à-pas complet (création du bot sur Discord, identifiants, réglages) est dans le guide de démarrage.
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
ruff check .
pytest
```

## Pistes d'amélioration

- Afficher les événements Google Agenda dans le briefing
- Dépenses récurrentes (abonnements) ajoutées automatiquement chaque mois
- Graphique de l'évolution du prix d'un article (l'historique est déjà enregistré)
- Dépenses partagées entre amis (qui doit combien à qui)
