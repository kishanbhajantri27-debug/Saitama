# Shop Showcase & CRM

Two surfaces over one Node server:

- **Customer app** (`public/index.html`, served at `/`) — browse what is available and what is coming, search and filter, request an item, and see the owner's answer.
- **Owner app** (`public/admin.html`, served at `/admin.html`) — publish items, approve or decline requests, keep customer records, and set the shop's branding. Password protected.

A customer never edits anything except their own contact details. Item name and price are fixed once listed: changing a listing someone has already seen is a delete and re-add, not an in-place edit.

## Running it

```bash
npm install
cp .env.example .env      # then fill it in
node server.js
```

Open <http://localhost:3000>. The owner app is at `/admin.html` and asks for the `ADMIN_USER` / `ADMIN_PASS` from your `.env`.

`.env` is gitignored and holds real credentials — never commit it. `.env.example` documents the keys and is safe to share.

Decision emails need SMTP settings in `.env`. Without them the app still runs: messages are composed and logged instead of delivered.

## Layout

| Path | What it holds |
|---|---|
| `server.js` | All HTTP routes and auth |
| `db.js` | SQLite schema and migrations |
| `mailer.js` | Decision emails |
| `public/index.html` | Customer app |
| `public/admin.html` | Owner app |
| `public/style.css` | Shared styling |

The database lives in `data/` and is gitignored. A fresh clone starts with an empty catalog — that is expected. Never commit the `.db` file; SQLite files conflict badly in git.

## Working on this together

Branches:

- `main` — always working. Merge into it, do not commit to it directly.
- `parent-app` — the owner app.
- `student-app` — the customer app.

The two apps are not separate codebases; they share `server.js`, `db.js`, and `style.css`. Splitting the work by **file** rather than by feature is what keeps merges cheap:

- Owner app work stays in `public/admin.html`.
- Customer app work stays in `public/index.html`.
- `server.js`, `db.js`, and `style.css` are shared. Say so before you change them.

`db.js` is the sharpest edge. Two people adding different columns to the same table will conflict every time, and a half-applied schema change breaks the other person's database rather than just their merge. Agree on schema changes before writing them.

Start work from an up-to-date `main`:

```bash
git checkout main && git pull
git checkout parent-app && git merge main
```

Then push your branch and open a pull request rather than merging into `main` yourself, so the other person sees what changed.
