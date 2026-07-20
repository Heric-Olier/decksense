import { useEffect, useState } from "react";
import { staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaTachometerAlt } from "react-icons/fa";
import { SECTIONS } from "./sections/registry";
import { TabBar } from "./sections/TabBar";
import { useShoulderNav } from "./sections/useShoulderNav";
import { useUpdate } from "./updater/useUpdate";
import { ensureFocusStyles } from "./focus";

function Content() {
  const sectionIds = SECTIONS.map((s) => s.id);
  const [active, setActive] = useState(SECTIONS[0].id);

  // Inject focus ring styles once on mount
  useEffect(() => {
    ensureFocusStyles();
  }, []);

  useShoulderNav({ ids: sectionIds, active, onSelect: setActive });
  const { status } = useUpdate();
  const alerts: Record<string, boolean> = {
    settings: status.state === "available",
  };

  const activeSection = SECTIONS.find((s) => s.id === active) ?? SECTIONS[0];
  const Active = activeSection.component;

  return (
    <>
      <TabBar sections={SECTIONS} active={active} onSelect={setActive} alerts={alerts} />
      <Active />
    </>
  );
}

export default definePlugin(() => {
  return {
    name: "DeckySense",
    titleView: <div className={staticClasses.Title}>DeckySense</div>,
    content: <Content />,
    icon: <FaTachometerAlt />,
    onDismount() {},
  };
});
