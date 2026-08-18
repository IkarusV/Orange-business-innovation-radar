# Flux RSS — Innovation Radar

Sources RSS pour la collecte de signaux externes (news, régulation, tendances marché, annonces techno), organisées par domaine Orange Business.

Statut : tous les liens ci-dessous ont été testés et confirmés fonctionnels. Les liens marqués **à vérifier** n'ont pas pu être confirmés avec certitude et doivent être testés avant intégration dans le pipeline.

---

## Tech & IT entreprise (signaux transversaux)

- ZDNet — https://www.zdnet.com/news/rss.xml
- The Register — https://www.theregister.com/headlines.atom
- Computerworld — https://www.computerworld.com/feed
- InfoWorld — https://www.infoworld.com/feed
- TechRepublic — https://www.techrepublic.com/rssfeeds/articles

## Cybersécurité

- Krebs on Security — https://krebsonsecurity.com/feed
- Dark Reading — https://www.darkreading.com/rss.xml
- The Hacker News — https://feeds.feedburner.com/TheHackersNews
- Help Net Security — https://www.helpnetsecurity.com/feed
- SecurityWeek — https://www.securityweek.com/feed
- Cybersecurity Dive — https://www.cybersecuritydive.com/feeds/news

## Cloud & Data Centers

- Azure Blog — https://azure.microsoft.com/en-us/blog/feed/
- AWS Blog — https://aws.amazon.com/blogs/aws/feed/
- Google Cloud Blog — https://cloudblog.withgoogle.com/rss

## Connectivity / Telecom / 5G

- RCR Wireless News — https://feeds.feedburner.com/rcrwireless/sLmV
- Schneider Electric Blog — 5G & Infrastructure — https://blog.se.com/tag/5g/feed/

## Smart Industries / IoT industriel

- Manufacturing Dive — https://www.manufacturingdive.com/feeds/news

## Régulation UE

EUR-Lex — pas d'URL fixe unique, donc pas listée comme flux ci-dessus (pour éviter une tentative automatique qui échouera à chaque run). Aller sur https://eur-lex.europa.eu, section "RSS feeds", et choisir la catégorie (législation Parlement/Conseil, Journal Officiel L, Journal Officiel C, propositions de la Commission). Utile pour les signaux type ESPR cités dans le brief Orange Business.

## Finance, Banking, Insurance

- Finextra — https://www.finextra.com/rss/headlines.aspx

## Healthcare / Lifesciences

- Healthcare Dive — https://www.healthcaredive.com/feeds/news
- Fierce Healthcare — https://www.fiercehealthcare.com/rss/xml
- BioPharma Dive — https://www.biopharmadive.com/feeds/news
- PharmaVoice — https://www.pharmavoice.com/feeds/news

## Retail

- Retail Dive — https://www.retaildive.com/feeds/news

## Public / Smart Cities

- Smart Cities Dive — https://www.smartcitiesdive.com/feeds/news

## Transportation & Construction

- Construction Dive — https://www.constructiondive.com/feeds/news
- Automotive World — https://www.automotiveworld.com/feed
- Automotive Dive — https://www.automotivedive.com/feeds/news — **à vérifier**
- Trucking Dive — https://www.truckingdive.com/feeds/news — **à vérifier**

## Energy / Natural Resources

- Utility Dive — https://www.utilitydive.com/feeds/news
- EIA — Today in Energy — https://www.eia.gov/rss/todayinenergy.xml

## CX / Marketing / Digital Transformation

- Marketing Dive — https://www.marketingdive.com/feeds/news — **à vérifier**
- CIO Dive — https://www.ciodive.com/feeds/news — **à vérifier**

## À compléter — pas de source fiable confirmée pour l'instant

- Aerospace & Defense (Aviation Week a un flux mais réservé aux abonnés AWIN ; Defense News a une page RSS à defensenews.com/m/rss/ mais pas d'URL de flux global claire — à tester)
- Media & Entertainment (Digiday — digiday.com/feed — couvre l'angle pub/martech mais pas broadcast/telco)

---

## Retiré de la liste

- **TechCrunch** — retiré de "Tech & IT entreprise" : flux trop généraliste grand public, signal/bruit faible pour le radar (confirmé lors de l'analyse du CSV d'articles).
- **Energy Central** — lien mort (page 404, site fermé ou restructuré).
- **Data Center Journal** — URL injoignable (status None, échec de connexion à chaque test).
- **Sierra Wireless Blog** — URL injoignable (status None, échec de connexion à chaque test).
- **Manufacturing & Logistics IT** — l'URL renvoie une page HTML d'index, pas un flux ; aucune URL de flux réelle trouvée.
- **Embedded Computing Design** — l'URL renvoie une page HTML, pas un flux ; aucune URL de flux fiable trouvée pour remplacer.

---

## Astuce pour combler les manques

Plusieurs sites appartiennent au même éditeur (famille "Industry Dive" : Healthcare Dive, BioPharma Dive, Retail Dive, Utility Dive, Manufacturing Dive, Construction Dive, Smart Cities Dive, Cybersecurity Dive, Marketing Dive, CIO Dive, Automotive Dive, Trucking Dive...) et suivent le même pattern d'URL `[nom]dive.com/feeds/news`.

Pour tout autre site sans lien RSS visible, tester dans l'ordre :
1. `/feed`
2. `/rss.xml`
3. `/feeds/news`

Ou chercher dans le `<head>` HTML de la page une balise `<link rel="alternate" type="application/rss+xml">`.
