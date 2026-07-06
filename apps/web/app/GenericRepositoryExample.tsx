"use client";

import {useEffect} from "react";

const PRIVATE_DEFAULTS = new Set(["BoneManTGRM/NICO", "bonemantgrm/nico"]);
const GENERIC_REPOSITORY_EXAMPLE = "your-org/your-repo";

function setNativeInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", {bubbles: true}));
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

export default function GenericRepositoryExample() {
  useEffect(() => {
    let attempts = 0;
    const applyGenericExample = () => {
      attempts += 1;
      document.querySelectorAll<HTMLInputElement>("input").forEach((input) => {
        const value = input.value.trim();
        if (PRIVATE_DEFAULTS.has(value)) setNativeInputValue(input, GENERIC_REPOSITORY_EXAMPLE);
        if (input.placeholder === "owner/repo") input.placeholder = GENERIC_REPOSITORY_EXAMPLE;
      });
      if (attempts >= 20) window.clearInterval(timer);
    };
    const timer = window.setInterval(applyGenericExample, 250);
    applyGenericExample();
    return () => window.clearInterval(timer);
  }, []);

  return null;
}
