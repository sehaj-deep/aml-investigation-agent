# AML Case Manager (UI)

React, TypeScript and Vite front end for the case API. Ant Design for components, Cytoscape.js for the case network.

- Development: `npm install`, then `npm run dev` (http://127.0.0.1:5173; `/api` is proxied to the API on port 8000).
- Docker: the `ui` service in `docker-compose.yml` builds this app and serves it with nginx on http://127.0.0.1:3000.

Screens: case queue, alert inbox, case workspace (network, evidence, pattern candidates, audit timeline, AI assessment, decision with the four-eyes rule), operations dashboard, model governance.

Identity is a local demo role switch (analyst, supervisor); there is no authentication.
