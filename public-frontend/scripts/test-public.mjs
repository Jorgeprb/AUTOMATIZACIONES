import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
const mainSource = await readFile(new URL("../src/main.tsx", import.meta.url), "utf8");

test("public CTAs connect registration and access", () => {
  assert.match(appSource, /https:\/\/client\.autogal\.es\/register/);
  assert.match(
    appSource,
    /\/auth\/login\/google\/start\?portal=client&return_to=\//,
  );
  assert.match(appSource, />\s*Registrarse/);
  assert.match(appSource, />\s*Acceder/);
  assert.doesNotMatch(appSource, /Solicitar una demo/i);
});

test("public legal routes remain connected", () => {
  for (const route of ["/aviso-legal", "/privacidad", "/cookies"]) {
    assert.match(mainSource, new RegExp(route));
    assert.match(appSource, new RegExp(`href=["']${route}["']`));
  }
});
