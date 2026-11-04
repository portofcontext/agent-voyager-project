/** Provider URLs and API-key headers for egress, metering, and credential proxies. */
import { ajv } from "../validation.js";
import * as modelsDev from "./_models_dev.js";

const FILE = "avp_endpoints.json";

export interface Auth {
  readonly header: string;
  readonly prefix: string;
}
export interface Endpoint {
  readonly base_url?: string | null;
  readonly auth?: Auth | null;
}
export interface Endpoints extends modelsDev.Snapshot {
  readonly providers: Record<string, Endpoint>;
}

const defaults = modelsDev.bundled(
  "avp_endpoint_defaults.json",
  (value) =>
    value as {
      gap_fillers: Record<string, string>;
      auth_by_package: Record<string, Auth>;
    },
);
export const GAP_FILLERS: Readonly<Record<string, string>> =
  defaults.gap_fillers;
/** Fixed API-key headers only; Bedrock means API keys, not SigV4. */
export const AUTH_BY_PACKAGE: Readonly<Record<string, Auth>> =
  defaults.auth_by_package;
export const BEARER: Auth = { header: "authorization", prefix: "Bearer " };

const validateEndpoints = ajv.compile({
  type: "object",
  additionalProperties: false,
  required: ["source", "fetched", "providers"],
  properties: {
    source: { type: "string" },
    fetched: { type: "string", format: "date-time" },
    providers: {
      type: "object",
      additionalProperties: {
        type: "object",
        additionalProperties: false,
        properties: {
          base_url: { type: ["string", "null"] },
          auth: {
            anyOf: [
              { type: "null" },
              {
                type: "object",
                additionalProperties: false,
                required: ["header"],
                properties: {
                  header: { type: "string" },
                  prefix: { type: "string", default: "" },
                },
              },
            ],
          },
        },
      },
    },
  },
});

function parseEndpoints(value: unknown): Endpoints {
  const endpoints = {
    source: modelsDev.API,
    ...(value as Record<string, unknown>),
  };
  if (!validateEndpoints(endpoints))
    throw new TypeError(ajv.errorsText(validateEndpoints.errors));
  // Apply Auth's empty-prefix default without changing the caller's objects.
  const providers = Object.fromEntries(
    Object.entries(endpoints.providers as Record<string, Endpoint>).map(
      ([id, endpoint]) => [
        id,
        {
          ...endpoint,
          ...(endpoint.auth == null
            ? {}
            : {
                auth: { ...endpoint.auth, prefix: endpoint.auth.prefix ?? "" },
              }),
        },
      ],
    ),
  );
  return { ...endpoints, providers } as Endpoints;
}

let bundled: Endpoints | undefined;
export function bundledEndpoints(): Endpoints {
  return (bundled ??= modelsDev.bundled(FILE, parseEndpoints));
}
export function defaultCachePath(): string {
  return modelsDev.cachePath(FILE);
}

export async function fetchEndpoints(
  catalog?: Record<string, unknown>,
  {
    fill = GAP_FILLERS,
    auth = AUTH_BY_PACKAGE,
  }: {
    fill?: Readonly<Record<string, string>>;
    auth?: Readonly<Record<string, Auth>>;
  } = {},
): Promise<Endpoints> {
  const providers: Record<string, Endpoint> = Object.create(null);
  for (const [id, value] of Object.entries(
    await modelsDev.fetchCatalog(catalog),
  )) {
    const provider = value as { api?: unknown; npm?: string | null };
    const base_url =
      typeof provider.api === "string" &&
      provider.api &&
      !provider.api.includes("${")
        ? provider.api
        : Object.hasOwn(fill, id)
          ? fill[id]
          : undefined;
    const keyAuth =
      provider.npm && Object.hasOwn(auth, provider.npm)
        ? auth[provider.npm]
        : undefined;
    if (base_url || keyAuth)
      providers[id] = {
        ...(base_url == null ? {} : { base_url }),
        ...(keyAuth == null ? {} : { auth: keyAuth }),
      };
  }
  return parseEndpoints({
    fetched: new Date().toISOString(),
    providers: Object.fromEntries(
      Object.keys(providers)
        .sort()
        .map((id) => [id, providers[id]]),
    ),
  });
}

export function saveEndpoints(
  endpoints: Endpoints,
  path = defaultCachePath(),
): Promise<string> {
  return modelsDev.save(endpoints, path);
}
/** Offline unless maxAgeMs requests a refresh; otherwise prefer the newer cache or bundle. */
export function loadEndpoints(
  path?: string,
  { maxAgeMs }: { maxAgeMs?: number } = {},
): Promise<Endpoints> {
  return modelsDev.load(path, {
    defaultPath: defaultCachePath(),
    maxAgeMs,
    parse: parseEndpoints,
    bundled: bundledEndpoints,
    fetch: () => fetchEndpoints(),
  });
}
export function defaultBaseUrl(
  endpoints: Endpoints,
  provider: string,
): string | undefined {
  return Object.hasOwn(endpoints.providers, provider)
    ? (endpoints.providers[provider].base_url ?? undefined)
    : undefined;
}
export function providerAuth(
  endpoints: Endpoints,
  provider: string,
): Auth | undefined {
  return Object.hasOwn(endpoints.providers, provider)
    ? (endpoints.providers[provider].auth ?? undefined)
    : undefined;
}
