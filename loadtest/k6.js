// k6 run loadtest/k6.js   (or: docker run --rm -i --network host grafana/k6 run - < loadtest/k6.js)
import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE_URL || "http://localhost:8001";

export const options = {
  vus: 50,
  duration: "1m",
  thresholds: { http_req_duration: ["p(95)<300"], http_req_failed: ["rate<0.01"] },
};

export default function () {
  const r1 = http.get(`${BASE}/api/state`);
  check(r1, { "state 200": (r) => r.status === 200 });
  const r2 = http.get(`${BASE}/api/recommendations`);
  check(r2, { "recommendations 200": (r) => r.status === 200 });
}
