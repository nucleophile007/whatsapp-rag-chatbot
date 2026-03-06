import { useMemo, useState, type DragEvent } from "react";
import { NODE_TYPES } from "../lib/flowSchema";
import { QUICK_FLOW_TEMPLATES } from "../lib/flowTemplates";
import { MessageSquare, Search, Send, FileText, Globe, Clock, Zap, CalendarClock, WandSparkles } from "lucide-react";

interface NodePaletteProps {
  width?: number;
}

const sections = [
  {
    title: "Triggers",
    tint: "border-cyan-200 bg-cyan-50 text-cyan-800",
    iconWrap: "bg-cyan-100 text-cyan-700",
    items: [
      { label: "On Message", nodeType: "trigger", subType: NODE_TYPES.TRIGGER.WHATSAPP_MESSAGE, icon: MessageSquare },
      { label: "On Mention", nodeType: "trigger", subType: NODE_TYPES.TRIGGER.WHATSAPP_MENTION, icon: MessageSquare },
      { label: "On Schedule", nodeType: "trigger", subType: NODE_TYPES.TRIGGER.SCHEDULE, icon: CalendarClock },
    ],
  },
  {
    title: "Conditions",
    tint: "border-amber-200 bg-amber-50 text-amber-800",
    iconWrap: "bg-amber-100 text-amber-700",
    items: [
      { label: "Text Contains", nodeType: "condition", subType: NODE_TYPES.CONDITION.TEXT_CONTAINS, icon: FileText },
      { label: "Text Not Empty", nodeType: "condition", subType: NODE_TYPES.CONDITION.TEXT_NOT_EMPTY, icon: FileText },
    ],
  },
  {
    title: "Actions",
    tint: "border-emerald-200 bg-emerald-50 text-emerald-800",
    iconWrap: "bg-emerald-100 text-emerald-700",
    items: [
      { label: "RAG Query", nodeType: "action", subType: NODE_TYPES.ACTION.RAG_QUERY, icon: Search },
      { label: "Send Message", nodeType: "action", subType: NODE_TYPES.ACTION.SEND_MESSAGE, icon: Send },
      { label: "Delay", nodeType: "action", subType: NODE_TYPES.ACTION.DELAY, icon: Clock },
      { label: "HTTP Request", nodeType: "action", subType: NODE_TYPES.ACTION.HTTP_REQUEST, icon: Globe },
    ],
  },
];

export default function NodePalette({ width }: NodePaletteProps) {
  const [search, setSearch] = useState("");

  const onDragStart = (event: DragEvent, nodeType: string, subType: string) => {
    event.dataTransfer.setData("application/reactflow", nodeType);
    event.dataTransfer.setData("application/subtype", subType);
    event.dataTransfer.effectAllowed = "move";
  };

  const onTemplateDragStart = (event: DragEvent, templateId: string) => {
    event.dataTransfer.setData("application/flow-template", templateId);
    event.dataTransfer.effectAllowed = "copyMove";
  };

  const filteredSections = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return sections;
    return sections
      .map((section) => ({
        ...section,
        items: section.items.filter(
          (item) =>
            item.label.toLowerCase().includes(query) ||
            item.subType.toLowerCase().includes(query) ||
            section.title.toLowerCase().includes(query)
        ),
      }))
      .filter((section) => section.items.length > 0);
  }, [search]);

  const filteredTemplates = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return QUICK_FLOW_TEMPLATES;
    return QUICK_FLOW_TEMPLATES.filter(
      (template) =>
        template.label.toLowerCase().includes(query) ||
        template.description.toLowerCase().includes(query) ||
        template.id.toLowerCase().includes(query)
    );
  }, [search]);

  return (
    <aside className="shrink-0 border-r border-border/70 bg-white/85 p-4 overflow-y-auto" style={width ? { width } : undefined}>
      <div className="mb-4 flex items-center gap-2">
        <div className="rounded-lg bg-primary/10 p-2 text-primary">
          <Zap className="h-4 w-4" />
        </div>
        <div>
          <h3 className="text-sm font-bold">Node Palette</h3>
          <p className="text-xs text-muted-foreground">Drag onto canvas</p>
        </div>
      </div>

      <div className="relative mb-4">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="input-base pl-9"
          placeholder="Search nodes..."
        />
      </div>

      <div className="space-y-5">
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Quick Flow Templates</h4>
          <div className="space-y-2">
            {filteredTemplates.map((template) => (
              <div
                key={template.id}
                draggable
                onDragStart={(event) => onTemplateDragStart(event, template.id)}
                className="cursor-grab rounded-xl border border-sky-200 bg-sky-50 p-3 text-sky-900 transition-shadow hover:shadow-sm active:cursor-grabbing"
              >
                <div className="flex items-start gap-3">
                  <div className="rounded-lg bg-sky-100 p-2 text-sky-700">
                    <WandSparkles className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold">{template.label}</p>
                    <p className="mt-0.5 text-xs text-sky-700/80">{template.description}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {filteredSections.map((section) => (
          <div key={section.title}>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{section.title}</h4>
            <div className="space-y-2">
              {section.items.map((item) => (
                <div
                  key={item.subType}
                  draggable
                  onDragStart={(e) => onDragStart(e, item.nodeType, item.subType)}
                  className={`cursor-grab rounded-xl border p-3 transition-shadow hover:shadow-sm active:cursor-grabbing ${section.tint}`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`rounded-lg p-2 ${section.iconWrap}`}>
                      <item.icon className="h-4 w-4" />
                    </div>
                    <span className="text-sm font-semibold">{item.label}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
        {filteredSections.length === 0 && filteredTemplates.length === 0 && (
          <p className="rounded-lg border border-dashed border-border/70 p-3 text-xs text-muted-foreground">No nodes match your search.</p>
        )}
      </div>
    </aside>
  );
}
