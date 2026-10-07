import { defineConfig } from 'wxt';
import tailwindcss from '@tailwindcss/vite';

// See https://wxt.dev/api/config.html
export default defineConfig({
    modules: ['@wxt-dev/module-react'],
    vite: () => ({
        plugins: [tailwindcss()],
        envDir: '../', // Reads .env from root workspace folder
    }),
    manifest: {
        permissions: ['identity', 'storage'],
        key: "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5O/4magJWSbb0dSdfoegA6s5ehs4H7PxRL1N/lOzZTFQT2xfu9ewUNbPXOXkugwEu82S8+Lk50ayej4bjAOR/74O3/gK2CzCwbJNWwxgcs23AgFOKzwztF2lm9XKWCS9c3qxHTejNvlYm+yJwU7g2CxBQU5xPWOlAAIIkKkgIh+X6tuWnMA/TIumKQsWRTLRQwycTc6XOCSag+almLSoKKhmxi39LD5Cfv2LMzBCWn+NbIBjnjR6ueoQLlC4f+edrLi/h8dksCU0xU5I3w7CsL/QCxltfRxobfnNorcSwJsiZ91sNMvm8joCq6uWAIdsGAu+E4SWbSj6fWI22I7vNQIDAQAB",
        browser_specific_settings: {
            gecko: {
                id: '{a9c80929-4b1d-414a-8e93-eb4017942ac9}',
            },
        },
    }
});
