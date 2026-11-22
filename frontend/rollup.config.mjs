import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
const plugins = () => [
  resolve(),
  typescript({
    noEmit: false,
    include: ["src/**/*.ts", "demo/**/*.ts"],
    exclude: ["**/*.test.ts"],
  }),
];
export default [
  {
    input: "src/card.ts",
    output: {
      file: "../custom_components/central_heating/frontend/central-heating-card.js",
      format: "es",
    },
    plugins: plugins(),
  },
  {
    input: "demo/demo.ts",
    output: { file: "demo/demo.js", format: "iife" },
    plugins: plugins(),
  },
];
