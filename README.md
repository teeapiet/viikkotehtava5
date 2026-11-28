# WEEK 5 AI CHAT

## Implementation and documentation

| Item | My implementation |
|---|---|
| Application | The chat runs on Server A at [http://195.148.23.163/viikko5/](http://195.148.23.163/viikko5/). |
| Repository | The application, tests and deployment configuration are in this [repository](https://github.com/teeapiet/viikkotehtava5). |
| Request path | Browser → Nginx → Gunicorn Unix socket → Flask → Ollama / MariaDB. |
| CI pipeline | Every push and pull request runs Ruff, pytest and shell syntax checks. Chat tests mock Ollama and use in-memory storage instead of the production database. The deploy job requires successful tests. See the [workflow](.github/workflows/ci-cd.yml) and [tests](test_app.py). |
| Automated deployment | Successful pushes to `main` deploy automatically. The workflow copies the code, installs dependencies, updates the server configuration, checks Nginx before reloading it and restarts only `chatapp`. It verifies the running SHA through the socket and public URL. |
| LLM chat | Flask sends messages to the local `qwen2.5:0.5b` model through Ollama and streams the response back to the browser. Ollama listens on `127.0.0.1:11434`. Gunicorn uses `/run/chatapp/gunicorn.sock`. |
| MariaDB history | Messages are stored in the `chatapp` database. The browser keeps a conversation ID and uses it to load history after a refresh. Separate browser sessions use separate conversation IDs. See the [schema](deploy/sql/schema.sql) and [database code](db.py). |
| Nginx sub-path and service | The page, styles, scripts and API use `/viikko5/`. I added a snippet to the existing Nginx site and kept the earlier locations. The [systemd service](deploy/systemd/chatapp.service) runs as `chatapp`. See the [Nginx configuration](deploy/nginx/chatapp.conf). |
| Users, database and secrets | The app has a dedicated non-login Linux user and its own database account. The database account has `SELECT`, `INSERT` and `DELETE` privileges on `chatapp` only. File permissions and grants are linked below. |
| Documentation and GitHub | The chat page links to this README. The repository includes setup instructions, server evidence and [descriptive commit history](https://github.com/teeapiet/viikkotehtava5/commits/main/). |
| Secrets | The database password stays in `/etc/chatapp/chatapp.env` on the server. Systemd loads the file. A separate deployment SSH key is used by GitHub Actions. Deployment credentials and the trusted host key are stored in Actions Secrets. Real passwords, tokens and private keys are not committed. |
| SSH access | SSH port 22 is open from `0.0.0.0/0`. This allows GitHub Actions to connect from its changing runner IP addresses, but also allows SSH connection attempts from any IPv4 address. Actions uses a separate deployment key stored in GitHub Actions Secrets. A leaked key would give access to the server, so it must be protected. The deployment key can be revoked without changing my personal SSH key. |
| Model choice | I chose `qwen2.5:0.5b` because it is small and suitable for the server. The [resource output](docs/checks/resources.txt) shows the model, memory usage with the model loaded, disk space. |
| Earlier assignments | The Week 5 configuration keeps the existing sites and services. Evidence: [Week 2](http://195.148.23.163/viikko2/) and [Week 4](http://86.50.231.16/viikko4/). |
| Replication | The `chatapp` database is not replicated to Server B. Server A has no database-level binlog filters, but Server B uses `Replicate_Wild_Do_Table: viikko2db.%`. This limits replication to tables in `viikko2db` and excludes `chatapp`. Both replication threads show `Yes`, and the database check confirms that `chatapp` is not present on Server B. |
| What I learned | I learned that permission to push application code is not enough to update workflow files. The GitHub token also needs permission to update workflows. |

## Tests

| Test | Result |
|---|---|
| Public chat | The [live application](http://195.148.23.163/viikko5/) is available for testing. |
| Persistent history | Messages are saved in MariaDB and loaded after a page refresh. |
| Separate browser sessions | The normal and private browser windows use separate conversations. |
| Local services | The [listener output](docs/checks/listeners.txt) shows local Ollama and the Gunicorn Unix socket. A TCP connection test from my Windows computer to `195.148.23.163:11434` returned `TcpTestSucceeded: False`. |
| Successful deployment 1 | [Open the successful workflow run](https://github.com/teeapiet/viikkotehtava5/actions/runs/45845553198). |
| Successful deployment 2 | [Open another successful workflow run](https://github.com/teeapiet/viikkotehtava5/actions/runs/45844868326). |
| Deployed version | The deployment writes GitHub’s commit SHA to `REVISION`. The [health endpoint](http://195.148.23.163/viikko5/health) returns it. |
| Failed test blocks deployment | The [failed workflow run](https://github.com/teeapiet/viikkotehtava5/actions/runs/46152884798) shows a failed test and a skipped deploy job. |
| Startup after reboot | The [reboot check](docs/checks/reboot.txt) records service status and health responses after restarting the server, before manually starting any services. |
| Nginx sub-path | The [HTTP checks](docs/checks/subpath.txt) cover the page, CSS, JavaScript and history API under `/viikko5/`. |

## Required server evidence

| Required information | Configuration and recorded output |
|---|---|
| Service status, user and group | The service uses `User=chatapp` and `Group=www-data`. The output of `systemctl status chatapp` and `systemctl show chatapp -p User -p Group` is in [service.txt](docs/checks/service.txt). |
| Application directory, environment file and socket permissions | The application is under `/opt/chatapp/app`, settings are in `/etc/chatapp/chatapp.env` and the socket is `/run/chatapp/gunicorn.sock`. Their ownership and permissions are shown in [permissions.txt](docs/checks/permissions.txt). |
| Database privileges | The application account is `chatapp` at `127.0.0.1`. Its `SHOW GRANTS` output is in [grants.txt](docs/checks/grants.txt). Authentication details are removed from the published output. |
| Installed and loaded model | `ollama list` and `ollama ps` are included in [resources.txt](docs/checks/resources.txt). |
| Memory and disk | `free -h` with the model loaded and `df -h /` are included in [resources.txt](docs/checks/resources.txt). |
| Listening services | `ss -ltnp` and the Unix socket check are included in [listeners.txt](docs/checks/listeners.txt). Gunicorn has no public TCP port. |

## Setup and deployment

This setup uses the existing Ubuntu Server A with working Nginx, MariaDB and Ollama. It also needs Python venv support, rsync, curl and openssl.

| Step | Command or configuration |
|---|---|
| Clone the project | `git clone https://github.com/teeapiet/viikkotehtava5.git` followed by `cd viikkotehtava5` |
| Create the development environment | `python3 -m venv .venv` |
| Install development dependencies | `.venv/bin/python -m pip install -r requirements-dev.txt` |
| Run checks | `.venv/bin/ruff check .` and `.venv/bin/python -m pytest` |
| Prepare Server A | `bash scripts/server-setup.sh` |
| Connect the Nginx snippet | Add `include snippets/chatapp.conf;` inside the existing site’s `server` block. Keep the other settings. |
| Check and reload Nginx | `sudo nginx -t && sudo systemctl reload nginx` |
| Configure deployment access | Create a separate SSH key pair and add its public key to the server’s `authorized_keys`. |
| Add repository secrets | `CPOUTA_HOST`, `CPOUTA_USER`, `CPOUTA_SSH_KEY` and `CPOUTA_KNOWN_HOSTS`. |
| Deploy | Push a change to `main`. Tests run first, followed by deployment. |
| Verify | Open `/viikko5/health` and compare it with the deployed commit SHA. |
