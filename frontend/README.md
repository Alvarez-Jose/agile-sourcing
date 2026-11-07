# Frontend Setup Instructions
### Install Packages
Make sure you have Node.js 26.3.0 (Latest) installed. \
If you haven't installed pnpm on this version of node.js yet, do so by running:
```sh
npm install -g corepack
corepack enable pnpm
```
Then to install all packages for this project, run:
```sh
cd frontend
pnpm install
```
### Running the extension
The backend and extension share `secret/.env` at the repository root. See
[auth setup](../docs/auth-setup.md) for environment variables and Admin credentials.
Restart WXT after changing that file.

To run the frontend, run the following command in the frontend folder:
```sh
pnpm dev
```
