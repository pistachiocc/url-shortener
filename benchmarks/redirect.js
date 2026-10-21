import http from "k6/http";
import { check } from "k6";

export const options = {
  vus: 10,
  duration: "30s",
  maxRedirects: 0,
  summaryTrendStats: [
    "avg",
    "med",
    "p(95)",
    "p(99)",
    "min",
    "max",
  ],
};

const code = __ENV.SHORT_CODE

if (!code) {
  throw new Error("SHORT_CODE is required");
}

export default function () {
  const response = http.get(
    `http://127.0.0.1:8000/${code}`,
    { redirects: 0 }
  );

  check(response, {
    "returns 302": (r) => r.status === 302,
  });
}
