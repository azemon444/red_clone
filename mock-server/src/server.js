import { createApp, logStartup } from "./app.js";

const PORT = Number(process.env.PORT || 9090);
const HOST = process.env.HOST || "0.0.0.0";

const app = await createApp();
logStartup(app);

app.listen(PORT, HOST);
