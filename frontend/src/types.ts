export type Mode = "auto" | "away" | "summer" | "manual";
export interface Settings {
  frost_temperature: number;
  hysteresis: number;
  away_temperature: number;
  override_default: "next_block" | "duration";
  override_minutes: number;
  sync_rooms_on_knob_change: boolean;
  retry_seconds: number;
}
export interface Profile {
  name: string;
  days: Record<string, { start: string; target: number }[]>;
}
export interface Room {
  name: string;
  trvs: string[];
  profile_id: string;
  area_id: string | null;
  enabled: boolean;
}
export interface Override {
  target: number;
  until: string;
  source: string;
}
export interface Configuration {
  settings: Settings;
  mode: { value: Mode; until: string | null };
  profiles: Record<string, Profile>;
  rooms: Record<string, Room>;
  overrides: Record<string, Override>;
  shadow: boolean;
}
export interface RoomStatus {
  name: string;
  current: number | null;
  desired: number | null;
  target?: number | null;
  trvs: Record<string, number | null>;
  demanding: boolean;
  sync_problem: boolean;
  override_until: string | null;
  next_change: string | null;
  next_target: number | null;
}
export interface Status {
  config_entry_id: string;
  room_entity_ids?: string[];
  used_trv_ids?: string[];
  configuration: Configuration;
  global: {
    demand_count: number;
    virtual_temp: number | null;
    virtual_temp_raw: number | null;
    virtual_setpoint: number;
    command: {
      heat: boolean;
      room_temperature: number | null;
      setpoint: number;
    };
    last_sent: string | null;
    shadow: boolean;
    mode: { value: Mode; until: string | null };
  };
  rooms: Record<string, RoomStatus>;
  saved_id?: string;
}
export interface Entry {
  entry_id: string;
  title: string;
}
export type Message = { type: string; [key: string]: unknown };
export interface Locale {
  language: string;
  time_format: "12" | "24" | "language" | "system";
  time_zone?: "local" | "server";
}
export type SubscriptionEvent = Status | { unloaded: true };
export interface Hass {
  locale?: Locale;
  config?: { time_zone: string };
  callWS<T>(message: Message): Promise<T>;
  connection: {
    connected?: boolean;
    addEventListener?(
      event: "disconnected" | "ready",
      listener: () => void,
    ): void;
    removeEventListener?(
      event: "disconnected" | "ready",
      listener: () => void,
    ): void;
    subscribeMessage<T>(
      callback: (value: T) => void,
      message: Message,
    ): Promise<() => void>;
  };
  states: Record<
    string,
    { state: string; attributes: Record<string, unknown> }
  >;
  user?: { is_admin: boolean };
  areas?: Record<string, { name: string }>;
}
export interface CardConfig {
  type: string;
  config_entry_id?: string;
  title?: string;
}
