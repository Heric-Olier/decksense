import {
  PanelSection,
  PanelSectionRow,
  staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaTachometerAlt } from "react-icons/fa";

function Content() {
  return (
    <>
      <PanelSection title="Display Studio">
        <PanelSectionRow>
          <div className={staticClasses.Text}>Not implemented yet.</div>
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Haptic Studio">
        <PanelSectionRow>
          <div className={staticClasses.Text}>Not implemented yet.</div>
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Game Profiles">
        <PanelSectionRow>
          <div className={staticClasses.Text}>Not implemented yet.</div>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  return {
    name: "DeckSense",
    titleView: <div className={staticClasses.Title}>DeckSense</div>,
    content: <Content />,
    icon: <FaTachometerAlt />,
    onDismount() {},
  };
});
