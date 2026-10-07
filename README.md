# 🤖 Jarvis — bot Discord d'assistance personnelle

Un bot Discord auto-hébergé qui me sert d'assistant au quotidien, sur mon serveur perso :
rappels, to-do list, briefing du matin, suivi du budget, alertes de prix, monitoring
et liste de lecture alimentée par une extension navigateur (dépôt `read-later-extension`).

![Python](https://img.shields.io/badge/python-3.12-blue) ![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2) ![SQLite](https://img.shields.io/badge/SQLite-async-003B57) ![Docker](https://img.shields.io/badge/docker-ready-2496ED)

## Fonctionnalités

| Module | Commandes | Ce que ça fait |
|---|---|---|
| ⏰ **Rappels** | `/rappel ajouter` `liste` `supprimer` | Dates en français naturel (`dans 2h`, `demain 9h`, `vendredi 18h`, `25/12`), récurrence quotidienne/hebdo/mensuelle, boutons « reporter » (+10 min, +1 h, demain) |
| 📝 **To-do** | `/todo ajouter` `liste` `fait` `supprimer` | Priorités, échéances, tâches en retard signalées |
| ☕ **Briefing** | `/brief` + envoi auto chaque matin | Météo (Open-Meteo), rappels du jour, tâches, budget du mois, articles à lire |
| 💶 **Budget** | `/depense` `/revenu` `/budget resume` `graphique` `historique` `limite` `export` `supprimer` | Dépenses par catégorie, plafonds mensuels avec alertes à 80 % / 100 %, graphique en anneau, export CSV compatible Excel |
| 🏷️ **Prix** | `/prix ajouter` `liste` `cible` `verifier` `supprimer` | Liste d'articles, plusieurs boutiques par article (meilleur prix 🥇), vérification toutes les X heures, alerte en cas de baisse ou de prix cible atteint, récap hebdo |
| 🖥️ **Monitoring** | `/status` `/site ajouter` `liste` `supprimer` | CPU, RAM, disque, température ; alertes au-delà d'un seuil ; surveillance de sites web avec alerte de panne et de retour en ligne |
| 📚 **À lire plus tard** | `/alire liste` `hasard` `lu` `ajouter` | Enregistre les liens postés par l'extension, ✅ en réaction pour marquer comme lu, digest du samedi matin |

## Points techniques

- **Architecture modulaire** : chaque fonctionnalité est un *cog* discord.py indépendant (`jarvis/cogs/`), chargé au démarrage.
- **Parseur de dates en français** maison ([`timeparse.py`](jarvis/utils/timeparse.py)), qui gère aussi les changements d'heure été/hiver pour les rappels récurrents.
- **Extraction de prix générique** ([`pricing.py`](jarvis/utils/pricing.py)) : données structurées JSON-LD schema.org → balises meta → sélecteurs connus → sélecteur CSS fourni par l'utilisateur. API officielle pour Steam.
- **SQLite asynchrone** (aiosqlite), montants stockés en centimes, dates en timestamps UTC affichées avec les timestamps dynamiques de Discord (`<t:…:R>`).
- **Tâches planifiées** avec `discord.ext.tasks` (heures fixes dans le fuseau configuré).
- **Accès restreint** au propriétaire via un `CommandTree` personnalisé, et gestion centralisée des erreurs de saisie.
- **Tests** (pytest, 85 cas), **lint** (ruff), **CI GitHub Actions**, **image Docker**.

## Installation

### 1. Créer le bot sur Discord

1. [Portail développeur Discord](https://discord.com/developers/applications) → **New Application**.
2. Onglet **Bot** → **Reset Token** → copie le token.
3. Toujours dans **Bot**, active **Message Content Intent** (nécessaire pour la liste de lecture).
4. Onglet **OAuth2 → URL Generator** : coche `bot` et `applications.commands`, puis les permissions
   *Send Messages*, *Embed Links*, *Attach Files*, *Add Reactions*, *Read Message History*.
   Ouvre l'URL générée pour inviter le bot sur ton serveur.
5. Dans Discord, active le **mode développeur** (Paramètres → Avancés) pour pouvoir copier les identifiants
   (clic droit → *Copier l'identifiant*) du serveur, des salons et de ton compte.

Salons conseillés : `#briefing`, `#alertes`, `#a-lire`.

### 2. Configurer

```bash
cp .env.example .env   # puis remplis DISCORD_TOKEN, GUILD_ID, OWNER_ID et les ID des salons
```

### 3. Lancer

**Avec Docker** (recommandé pour un serveur / Raspberry Pi) :

```bash
docker compose up -d --build
docker compose logs -f
```

**Sans Docker** :

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS : source .venv/bin/activate)
pip install -r requirements.txt
python -m jarvis
```

### Tests

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## Exemples

```
/rappel ajouter quand: demain 8h30 message: Appeler le garage
/rappel ajouter quand: 1er novembre 9h message: Payer le loyer repeter: Tous les mois
/todo ajouter tache: Finir le rapport priorite: 🔴 Haute echeance: vendredi
/depense montant: 23,90 categorie: Restaurant description: Sushis
/budget limite categorie: Restaurant montant: 150
/prix ajouter article: Écran 27" url: https://… prix_cible: 199
/site ajouter url: https://mon-portfolio.fr
```

## Structure

```
jarvis/
├── __main__.py        # point d'entrée
├── bot.py             # classe Jarvis, chargement des modules, gestion d'erreurs
├── config.py          # configuration via .env
├── db.py              # schéma SQLite et accès asynchrone
├── cogs/              # un fichier par fonctionnalité
└── utils/             # parsing des dates, montants, prix (testé unitairement)
tests/
```

## Pistes d'amélioration

- Synchronisation Google Calendar dans le briefing
- Dépenses récurrentes (abonnements) saisies automatiquement chaque mois
- Graphique d'historique pour chaque article suivi
- Dépenses partagées entre amis (qui doit combien à qui)
