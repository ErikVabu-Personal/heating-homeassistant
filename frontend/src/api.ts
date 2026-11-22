import type { Entry, Hass, Message, Status } from "./types";
export class HeatingClient {
  constructor(
    private hass: Hass,
    public entryId: string,
  ) {}
  static async entries(hass: Hass): Promise<Entry[]> {
    return (
      await hass.callWS<{ entries: Entry[] }>({ type: "central_heating/get" })
    ).entries;
  }
  get(): Promise<Status> {
    return this.hass.callWS(this.message("get"));
  }
  subscribe(callback: (status: Status) => void): Promise<() => void> {
    return this.hass.connection.subscribeMessage(
      callback,
      this.message("subscribe"),
    );
  }
  write(
    command: string,
    fields: Record<string, unknown> = {},
  ): Promise<Status> {
    return this.hass.callWS(this.message(command, fields));
  }
  private message(
    command: string,
    fields: Record<string, unknown> = {},
  ): Message {
    return {
      ...fields,
      type: `central_heating/${command}`,
      config_entry_id: this.entryId,
    };
  }
}
export function overridePayload(
  roomId: string,
  temperature: number,
  duration: string,
  customMinutes?: number,
): Record<string, unknown> {
  if (
    !Number.isFinite(temperature) ||
    temperature < 5 ||
    temperature > 30 ||
    !Number.isInteger(temperature * 2)
  )
    throw new Error("Choose a target from 5 to 30 °C in 0.5° steps.");
  const data: Record<string, unknown> = {
    room_id: roomId,
    temperature,
    kind: duration === "next_block" ? "next_block" : "duration",
  };
  if (duration !== "next_block") {
    const minutes = duration === "custom" ? customMinutes : Number(duration);
    if (
      !minutes ||
      !Number.isInteger(minutes) ||
      minutes < 1 ||
      minutes > 10080
    )
      throw new Error("Choose 1 to 10080 minutes.");
    data.minutes = minutes;
  }
  return data;
}
