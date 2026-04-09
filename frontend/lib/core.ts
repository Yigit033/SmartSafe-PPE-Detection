import { CoreServiceClient } from "./coreClient";

// Environment variable for Core backend URL
const CORE_URL = process.env.NEXT_PUBLIC_CORE_URL || "http://localhost:5577";

/**
 * Global Core Client instance.
 * Mirrored after Encore api singleton.
 */
const core = new CoreServiceClient(CORE_URL);

export default core;
