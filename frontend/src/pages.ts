import {
  Activity, BookOpen, ChartNoAxesCombined, CircuitBoard, LayoutDashboard, RadioTower, SlidersHorizontal,
} from "lucide-react";

export const pages = [
  { id: "overview", name: "Overview", title: "Network overview", group: "Workspace", Icon: LayoutDashboard,
    description: "Explore handover activity and controller performance across the LTE benchmark." },
  { id: "topology", name: "Topology replay", title: "Topology replay", group: "Workspace", Icon: RadioTower,
    description: "Follow a recorded run through the network, one handover at a time." },
  { id: "events", name: "Handover events", title: "Handover events", group: "Workspace", Icon: Activity,
    description: "Inspect connection requests and outcomes at their recorded timestamps." },
  { id: "comparison", name: "Policy comparison", title: "Policy comparison", group: "Analysis", Icon: ChartNoAxesCombined,
    description: "Compare controller results under matching speed and run conditions." },
  { id: "model-evaluation", name: "Model evaluation", title: "Model evaluation", group: "Analysis", Icon: CircuitBoard,
    description: "Try XGBoost and Logistic Regression and review the training results." },
  { id: "methodology", name: "Methodology", title: "Methodology", group: "Analysis", Icon: BookOpen,
    description: "Read how the benchmark was recorded and what each measurement represents." },
  { id: "simulation-control", name: "Live simulation", title: "Live simulation", group: "Execution", Icon: SlidersHorizontal,
    description: "Configure an ns-3 experiment and follow its execution on the simulation server." },
] as const;

export type Page = typeof pages[number];
export type PageId = Page["id"];
export const pageFromHash = () => pages.find(page => page.id === window.location.hash.slice(1)) ?? pages[0];
