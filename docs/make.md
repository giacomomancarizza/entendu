# Getting the sheet on my phone with Make.com

`entendu process ... --send` posts the study sheet to a Make.com webhook. Make then delivers it
wherever I read on the metro. My scenario has three modules:

1. **Webhooks > Custom webhook**. Create it, copy the URL into `.env` as `MAKE_WEBHOOK_URL`,
   then click "Redetermine data structure" and run `entendu process ... --send` once so Make
   learns the payload.
2. **Gmail > Send an email** to myself:
   - Subject: `{{subject}}`
   - Content type: HTML, Content: `{{html}}`
3. Optional, **Notion > Create a database item** inside an **Iterator** over `{{items}}`,
   to keep every word and expression in a Notion table (columns: Kind, Text, Meaning, Example).

## Payload

```json
{
  "subject": "Entendu: Le Café du Lundi, Camille et son appli anti abonnements",
  "podcast": "Le Café du Lundi",
  "episode": "Camille et son appli anti abonnements",
  "published": null,
  "counts": {"words": 10, "expressions": 14, "moments": 5},
  "html": "<!doctype html>...",
  "markdown": "# Le Café du Lundi: ...",
  "items": [
    {"kind": "expression", "text": "péter les plombs", "meaning": "dare di matto, esaurirsi",
     "example": "Et dormez, quand même, sinon vous allez péter les plombs."}
  ]
}
```
