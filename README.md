# Jarvis

Bot Discord d'assistance personnelle.

## Fonctionnalités

- **Rappels** en français naturel (« dans 2h », « demain 9h », « vendredi 18h »), qui peuvent se répéter
- **To-do list** avec priorités et échéances
- **Briefing du matin** : météo, rappels, tâches, budget
- **Budget** : dépenses par catégorie, plafonds, graphique, export CSV
- **Suivi de prix** avec alerte quand un prix baisse
- **Monitoring** de la machine et de sites web
- **Liste de lecture**, alimentée par l'extension « À lire plus tard »

## Commandes

| Commande | Rôle |
|---|---|
| `/rappel ajouter` `liste` `supprimer` | Rappels |
| `/todo ajouter` `liste` `fait` `supprimer` | Tâches |
| `/brief` | Briefing du jour |
| `/depense` `/revenu` | Noter une dépense ou une rentrée d'argent |
| `/budget resume` `graphique` `historique` `limite` `export` `supprimer` | Budget |
| `/prix ajouter` `liste` `cible` `verifier` `supprimer` | Suivi de prix |
| `/status` `/site ajouter` `liste` `supprimer` | Monitoring |
| `/alire liste` `hasard` `lu` `ajouter` | Liste de lecture |

## Lancer

```bash
pip install -r requirements.txt
cp .env.example .env    # puis remplis le fichier
python bot.py
```
