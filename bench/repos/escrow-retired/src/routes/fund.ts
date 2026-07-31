import { CUSTODY_RETIRED } from "../custody";
export function fund(req, res) {
  if (CUSTODY_RETIRED) {
    return res.status(410).json({ error: "on-chain USDC escrow custody retired" });
  }
}
