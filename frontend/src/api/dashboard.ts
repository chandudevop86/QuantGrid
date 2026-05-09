import API from "./client";

export const api = {
  health: () => API.get("/health").then(r => r.data),

  // ✅ FIXED
  getStrategies: () => API.get("/strategies").then(r => r.data),

  // ✅ FIXED
  runSignals: (payload: any) =>
    API.post("/signals", payload).then(r => r.data),

  // ✅ FIXED
  executeOrder: (payload: any) =>
    API.post("/order", payload).then(r => r.data),

  // optional
  getPrice: () => API.get("/price").then(r => r.data),
};
useLive((data) => {
  console.log("LIVE:", data);
});


