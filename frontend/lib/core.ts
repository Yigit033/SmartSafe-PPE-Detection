import { CoreServiceClient } from "./coreClient";

// Environment variable for Core backend URL
const CORE_URL = 
    process.env.NEXT_PUBLIC_CORE_URL || 
    (process.env.NODE_ENV === "production" 
        ? (typeof window !== "undefined" ? window.location.origin + "/core" : "/core") 
        : "http://localhost:5577");

/**
 * Returns the Core API base URL (client-side safe).
 * Dev: http://localhost:5577, Prod (nginx): origin + "/core"
 */
export function getCoreBaseUrl(): string {
    if (process.env.NEXT_PUBLIC_CORE_URL) return process.env.NEXT_PUBLIC_CORE_URL;
    if (process.env.NODE_ENV === "production") {
        return typeof window !== "undefined" ? window.location.origin + "/core" : "/core";
    }
    return "http://localhost:5577";
}

/**
 * Global Core Client instance.
 * Mirrored after Encore api singleton.
 */
const core = new CoreServiceClient(CORE_URL);

export default core;
