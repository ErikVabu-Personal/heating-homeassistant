import { describe, it, expect, vi } from "vitest";
import { HeatingClient, overridePayload } from "./api";
import type { Hass } from "./types";
describe("websocket client", () => {
  it("scopes commands, sends read/list and propagates write errors", async () => {
    const callWS = vi
      .fn()
      .mockResolvedValueOnce({ entries: [] })
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error("Denied"));
    const hass = { callWS } as unknown as Hass;
    expect(await HeatingClient.entries(hass)).toEqual([]);
    const client = new HeatingClient(hass, "entry_a");
    await client.get();
    expect(callWS).toHaveBeenLastCalledWith({
      type: "central_heating/get",
      config_entry_id: "entry_a",
    });
    await expect(client.write("mode/set", { mode: "auto" })).rejects.toThrow(
      "Denied",
    );
  });
  it("returns unsubscribe and preserves server messages", async () => {
    const unsubscribe = vi.fn();
    const subscribeMessage = vi.fn().mockResolvedValue(unsubscribe);
    const hass = { connection: { subscribeMessage } } as unknown as Hass;
    const callback = vi.fn();
    expect(await new HeatingClient(hass, "entry_a").subscribe(callback)).toBe(
      unsubscribe,
    );
    expect(subscribeMessage).toHaveBeenCalledWith(callback, {
      type: "central_heating/subscribe",
      config_entry_id: "entry_a",
    });
  });
});
describe("override payloads", () => {
  it("omits duration for next target change", () =>
    expect(overridePayload("room_a", 21.5, "next_block")).toEqual({
      room_id: "room_a",
      temperature: 21.5,
      kind: "next_block",
    }));
  it.each(["60", "120", "180"])("uses %s minutes", (duration) =>
    expect(overridePayload("room_a", 22, duration).minutes).toBe(
      Number(duration),
    ),
  );
  it("supports custom durations and rejects invalid steps/bounds", () => {
    expect(overridePayload("room_a", 22, "custom", 37).minutes).toBe(37);
    for (const target of [4, 31, 21.1, NaN])
      expect(() => overridePayload("room_a", target, "60")).toThrow();
    for (const minutes of [0, 10081, 1.2])
      expect(() => overridePayload("room_a", 22, "custom", minutes)).toThrow();
  });
});

it("write payload fields cannot replace command type or config entry identity (C05)", async () => {
  const callWS = vi.fn().mockResolvedValue({});
  const client = new HeatingClient({ callWS } as unknown as Hass, "entry_a");
  await client.write("mode/set", {
    type: "central_heating/room/delete",
    config_entry_id: "entry_b",
    mode: "auto",
  });
  expect(callWS).toHaveBeenCalledWith({
    type: "central_heating/mode/set",
    config_entry_id: "entry_a",
    mode: "auto",
  });
});
