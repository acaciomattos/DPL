(function () {
  const PAYLOAD_INPUT_ID = "rule-library-dnd-payload";
  const LIBRARY_ID = "rule-library";
  const PLACEHOLDER_CLASS = "dnd-placeholder";

  let activeDragCard = null;

  function getPayloadInput() {
    return document.getElementById(PAYLOAD_INPUT_ID);
  }

  function setReactInputValue(input, value) {
    const prototype = Object.getPrototypeOf(input);
    const descriptor =
      Object.getOwnPropertyDescriptor(prototype, "value") ||
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    const setter = descriptor && descriptor.set;
    const lastValue = input.value;
    if (setter) {
      setter.call(input, value);
    } else {
      input.value = value;
    }
    if (input._valueTracker) {
      input._valueTracker.setValue(lastValue);
    }
  }

  function dispatchPayload(payload) {
    const input = getPayloadInput();
    if (!input) {
      return;
    }
    const nextValue = JSON.stringify({
      ...payload,
      emitted_at: new Date().toISOString(),
    });
    setReactInputValue(input, nextValue);
    input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  }

  function ensurePlaceholder(panel) {
    let placeholder = panel.querySelector(`.${PLACEHOLDER_CLASS}`);
    if (!placeholder) {
      placeholder = document.createElement("div");
      placeholder.className = PLACEHOLDER_CLASS;
    }
    return placeholder;
  }

  function clearPlaceholders() {
    document.querySelectorAll(`.${PLACEHOLDER_CLASS}`).forEach((node) => node.remove());
    document.querySelectorAll(".dnd-dropzone.is-drop-active").forEach((node) => {
      node.classList.remove("is-drop-active");
    });
    document.querySelectorAll(".dnd-card.is-dragging").forEach((node) => {
      node.classList.remove("is-dragging");
    });
  }

  function panelCards(panel) {
    return Array.from(panel.querySelectorAll(".dnd-card")).filter(
      (card) => card !== activeDragCard
    );
  }

  function nearestCardForY(panel, clientY) {
    const cards = panelCards(panel);
    let nearest = null;
    let bestOffset = Number.NEGATIVE_INFINITY;
    cards.forEach((card) => {
      const box = card.getBoundingClientRect();
      const offset = clientY - box.top - box.height / 2;
      if (offset < 0 && offset > bestOffset) {
        bestOffset = offset;
        nearest = card;
      }
    });
    return nearest;
  }

  function placePlaceholder(panel, clientY) {
    const placeholder = ensurePlaceholder(panel);
    const nextCard = nearestCardForY(panel, clientY);
    if (nextCard) {
      panel.insertBefore(placeholder, nextCard);
    } else {
      panel.appendChild(placeholder);
    }
  }

  function nearestCardSibling(placeholder, direction) {
    let node = placeholder;
    while (node) {
      node = direction === "next" ? node.nextElementSibling : node.previousElementSibling;
      if (!node) {
        return null;
      }
      if (node.classList && node.classList.contains("dnd-card")) {
        return node;
      }
    }
    return null;
  }

  function bindCard(card) {
    if (card.dataset.dndBound === "true") {
      return;
    }
    card.dataset.dndBound = "true";
    card.addEventListener("dragstart", (event) => {
      activeDragCard = card;
      card.classList.add("is-dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.dataset.assetId || "");
      }
    });
    card.addEventListener("dragend", () => {
      activeDragCard = null;
      clearPlaceholders();
    });
  }

  function bindPanel(panel) {
    if (panel.dataset.dndBound === "true") {
      return;
    }
    panel.dataset.dndBound = "true";

    panel.addEventListener("dragover", (event) => {
      if (!activeDragCard) {
        return;
      }
      event.preventDefault();
      panel.classList.add("is-drop-active");
      if (panel.dataset.panel === "used") {
        placePlaceholder(panel, event.clientY);
      }
    });

    panel.addEventListener("dragleave", (event) => {
      if (!panel.contains(event.relatedTarget)) {
        panel.classList.remove("is-drop-active");
      }
    });

    panel.addEventListener("drop", (event) => {
      if (!activeDragCard) {
        return;
      }
      event.preventDefault();
      const sourceAssetId = activeDragCard.dataset.assetId || "";
      const sourcePanel = activeDragCard.dataset.panel || "";
      const targetPanel = panel.dataset.panel || "";
      let targetAssetId = null;
      let placement = "append";

      if (targetPanel === "used") {
        const placeholder = panel.querySelector(`.${PLACEHOLDER_CLASS}`);
        if (placeholder) {
          const nextCard = nearestCardSibling(placeholder, "next");
          const previousCard = nearestCardSibling(placeholder, "previous");
          if (nextCard) {
            targetAssetId = nextCard.dataset.assetId || null;
            placement = "before";
          } else if (previousCard) {
            targetAssetId = previousCard.dataset.assetId || null;
            placement = "after";
          }
        }
      }

      clearPlaceholders();
      dispatchPayload({
        asset_id: sourceAssetId,
        source_panel: sourcePanel,
        target_panel: targetPanel,
        target_asset_id: targetAssetId,
        placement: placement,
      });
    });
  }

  function initRuleLibraryDnD() {
    const library = document.getElementById(LIBRARY_ID);
    if (!library) {
      return;
    }
    library.querySelectorAll(".dnd-card").forEach(bindCard);
    library.querySelectorAll(".dnd-dropzone").forEach(bindPanel);
  }

  const observer = new MutationObserver(() => {
    window.requestAnimationFrame(initRuleLibraryDnD);
  });

  window.addEventListener("load", () => {
    initRuleLibraryDnD();
    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  });
})();
