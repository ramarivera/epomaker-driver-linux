const DOM = {
  Backspace: 42,
  Tab: 43,
  CapsLock: 57,
  Enter: 40,
  ShiftLeft: 225,
  ShiftRight: 229,
  ControlLeft: 224,
  MetaLeft: 227,
  AltLeft: 226,
  Space: 44,
  AltRight: 230,
  Backslash: 49,
  Escape: 41,
  Backquote: 53,
  Minus: 45,
  Equal: 46,
  BracketLeft: 47,
  BracketRight: 48,
  Semicolon: 51,
  Quote: 52,
  ArrowLeft: 80,
  ArrowDown: 81,
  ArrowUp: 82,
  PageUp: 75,
  PageDown: 78,
  ArrowRight: 79,
  Comma: 54,
  Period: 55,
  Slash: 56,
  PrintScreen: 70,
  End: 77,
  Insert: 73,
  Home: 74,
  Delete: 76,
};
for (let i = 0; i < 26; i++) DOM[`Key${String.fromCharCode(65 + i)}`] = i + 4;
for (let i = 1; i <= 9; i++) DOM[`Digit${i}`] = i + 29;
DOM.Digit0 = 39;
for (let i = 1; i <= 12; i++) DOM[`F${i}`] = 57 + i;
const SPECIAL = {
  Fn: [10, 1, 0, 0],
  AudioVolumeDown: [3, 0, 234, 0],
  AudioVolumeUp: [3, 0, 233, 0],
  MediaPlayPause: [3, 0, 205, 0],
};

export function layoutKeys(catalog) {
  return Object.entries(catalog.layout.layout).map(([name, geometry]) => {
    const isSpecial = Object.hasOwn(SPECIAL, name);
    const isDom = Object.hasOwn(DOM, name);
    if (!isSpecial && !isDom) {
      return { name, geometry, slot: null };
    }
    const action = isSpecial ? SPECIAL[name] : [0, 0, DOM[name], 0];
    const slot = Array.from({ length: 128 }, (_, i) => i).find((candidate) =>
      action.every((n, j) => catalog.matrices[0][candidate * 4 + j] === n),
    );
    return { name, geometry, slot: slot ?? null };
  });
}
