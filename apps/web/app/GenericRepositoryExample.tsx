"use client";

import {useEffect} from "react";

const PRIVATE_DEFAULTS = new Set(["BoneManTGRM/NICO", "bonemantgrm/nico"]);
const GENERIC_REPOSITORY_EXAMPLE = "your-org/your-repo";
const HERO_COPY = {
  eyebrow: "NICO",
  title: "Authorized assessment & repair intelligence",
  lead: "Evidence-bound code, dependency, CI/CD, QA, scanner, report, and repair workflows for authorized systems only.",
  actions: ["Run Assessment", "Scanner Worker", "Repair Intelligence", "How to Use"],
};

function setNativeInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", {bubbles: true}));
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

function applyGenericRepositoryExample() {
  document.querySelectorAll<HTMLInputElement>("input").forEach((input) => {
    const value = input.value.trim();
    if (PRIVATE_DEFAULTS.has(value)) setNativeInputValue(input, GENERIC_REPOSITORY_EXAMPLE);
    if (input.placeholder === "owner/repo") input.placeholder = GENERIC_REPOSITORY_EXAMPLE;
  });
}

function applyHeroCopy() {
  const hero = document.querySelector<HTMLElement>(".hero");
  if (!hero) return;
  const eyebrow = hero.querySelector<HTMLElement>(".eyebrow");
  const title = hero.querySelector<HTMLElement>("h1");
  const lead = hero.querySelector<HTMLElement>(".lead");
  if (eyebrow) eyebrow.textContent = HERO_COPY.eyebrow;
  if (title) title.textContent = HERO_COPY.title;
  if (lead) lead.textContent = HERO_COPY.lead;
  hero.querySelectorAll<HTMLAnchorElement>(".hero-actions a").forEach((anchor, index) => {
    if (HERO_COPY.actions[index]) anchor.textContent = HERO_COPY.actions[index];
  });
}

export default function GenericRepositoryExample() {
  useEffect(() => {
    let attempts = 0;
    const applyHostedUiPolish = () => {
      attempts += 1;
      applyGenericRepositoryExample();
      applyHeroCopy();
      if (attempts >= 20) window.clearInterval(timer);
    };
    const timer = window.setInterval(applyHostedUiPolish, 250);
    applyHostedUiPolish();
    return () => window.clearInterval(timer);
  }, []);

  return null;
}
