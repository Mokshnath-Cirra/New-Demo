# Put AURA AI on GitHub and make it a live website

GitHub Pages only serves static files, so it cannot run the Python API or the model. The setup below keeps your **code on GitHub** and runs the **live site on Render** (free tier), which redeploys on every `git push`.

## 1. Push to GitHub
1. Create an empty repository on github.com (for example `aura-ai`). Do not add a README there.
2. In the project folder:
   ```bash
   git init
   git add .
   git commit -m "AURA Predictive AI"
   git branch -M main
   git remote add origin https://github.com/<your-username>/aura-ai.git
   git push -u origin main
   ```
3. Optional: put the real `ai4i2020.csv` in `data/` before committing so the live model trains on the UCI data.
   `.env` and trained model files are git-ignored; the model is trained during the Render build.

## 2. Deploy on Render
1. Sign in at render.com with GitHub.
2. **New > Blueprint**, pick your `aura-ai` repository. Render reads `render.yaml` and creates the web service plus a PostgreSQL database.
3. Click **Apply**. The first build takes a few minutes (it installs packages and trains the model).
4. Open the `https://aura-ai-xxxx.onrender.com` URL shown on the service page. Check `/api/health` returns `"model_loaded": true`.

Free-tier notes: the service sleeps after ~15 minutes idle and takes about a minute to wake; the free database expires after a limited period, so use a paid plan for anything permanent.

## 3. Before sharing the link
- Anyone can run evaluations while `REQUIRE_AUTH` is `false`. To require sign-in, set `REQUIRE_AUTH=true` in Render > Environment; the admin username is `admin` and the password is the generated `DEMO_ADMIN_PASSWORD` value.
- Custom domain: Render > Settings > Custom Domains, then add the CNAME record they show. HTTPS is automatic.
- The machine connection and live stream are simulated (see README, "Important notes").

## Other hosts
Railway and Fly.io work the same way using the root `Dockerfile` (they provide `PORT` and a Postgres `DATABASE_URL`; both are handled). For a VPS, follow README section 3.
