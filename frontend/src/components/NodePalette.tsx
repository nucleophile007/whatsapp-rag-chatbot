import { type DragEvent } from 'react';
import { NODE_TYPES } from '../lib/flowSchema';
import { MessageSquare, Search, Send, FileText, Globe, Clock } from 'lucide-react';

export default function NodePalette() {
    const onDragStart = (event: DragEvent, nodeType: string, subType: string) => {
        event.dataTransfer.setData('application/reactflow', nodeType);
        event.dataTransfer.setData('application/subtype', subType);
        event.dataTransfer.effectAllowed = 'move';
    };

    return (
        <div className="w-64 border-r bg-white p-4 flex flex-col gap-6 overflow-y-auto">
            <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Triggers</h3>
                <div className="flex flex-col gap-2">
                    <div
                        className="flex items-center gap-3 p-3 bg-purple-50 border border-purple-100 rounded-lg cursor-grab hover:shadow-md transition-all active:cursor-grabbing"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'trigger', NODE_TYPES.TRIGGER.WHATSAPP_MENTION)}
                    >
                        <div className="bg-purple-100 p-2 rounded-md">
                            <MessageSquare className="h-4 w-4 text-purple-600" />
                        </div>
                        <span className="text-sm font-medium text-purple-900">On Mention</span>
                    </div>
                </div>
            </div>

            <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Conditions</h3>
                <div className="flex flex-col gap-2">
                    <div
                        className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-100 rounded-lg cursor-grab hover:shadow-md transition-all active:cursor-grabbing"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'condition', NODE_TYPES.CONDITION.TEXT_CONTAINS)}
                    >
                        <div className="bg-blue-100 p-2 rounded-md">
                            <FileText className="h-4 w-4 text-blue-600" />
                        </div>
                        <span className="text-sm font-medium text-blue-900">Text Contains</span>
                    </div>
                </div>
            </div>

            <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Actions</h3>
                <div className="flex flex-col gap-2">
                    <div
                        className="flex items-center gap-3 p-3 bg-green-50 border border-green-100 rounded-lg cursor-grab hover:shadow-md transition-all active:cursor-grabbing"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'action', NODE_TYPES.ACTION.RAG_QUERY)}
                    >
                        <div className="bg-green-100 p-2 rounded-md">
                            <Search className="h-4 w-4 text-green-600" />
                        </div>
                        <span className="text-sm font-medium text-green-900">RAG Query</span>
                    </div>

                    <div
                        className="flex items-center gap-3 p-3 bg-green-50 border border-green-100 rounded-lg cursor-grab hover:shadow-md transition-all active:cursor-grabbing"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'action', NODE_TYPES.ACTION.SEND_MESSAGE)}
                    >
                        <div className="bg-green-100 p-2 rounded-md">
                            <Send className="h-4 w-4 text-green-600" />
                        </div>
                        <span className="text-sm font-medium text-green-900">Send Message</span>
                    </div>

                    <div
                        className="flex items-center gap-3 p-3 bg-green-50 border border-green-100 rounded-lg cursor-grab hover:shadow-md transition-all active:cursor-grabbing"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'action', NODE_TYPES.ACTION.DELAY)}
                    >
                        <div className="bg-green-100 p-2 rounded-md">
                            <Clock className="h-4 w-4 text-green-600" />
                        </div>
                        <span className="text-sm font-medium text-green-900">Delay</span>
                    </div>

                    <div
                        className="flex items-center gap-3 p-3 bg-green-50 border border-green-100 rounded-lg cursor-grab hover:shadow-md transition-all active:cursor-grabbing"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'action', NODE_TYPES.ACTION.HTTP_REQUEST)}
                    >
                        <div className="bg-green-100 p-2 rounded-md">
                            <Globe className="h-4 w-4 text-green-600" />
                        </div>
                        <span className="text-sm font-medium text-green-900">HTTP Request</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
