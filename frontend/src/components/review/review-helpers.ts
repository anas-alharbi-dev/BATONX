import type { ApiRequestError } from "@/lib/api/client";

/** Turn an `invalid_*` envelope's details into a one-line message for the edited section. */
export function fieldMessage(error: ApiRequestError): string {
  const details = error.details as
    | { errors?: { loc: string; msg: string }[]; unknown?: string[] }
    | undefined;
  if (details?.errors?.length) {
    const first = details.errors[0];
    return `${first.msg}${first.loc ? ` (${first.loc})` : ""}`;
  }
  if (details?.unknown?.length) {
    return `Unknown section: ${details.unknown.join(", ")}`;
  }
  return error.message;
}
