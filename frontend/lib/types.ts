export interface Citation {
  source: string;
  gazette_id: string | null;
  part: string | null;
  section: string | null;
  notification_date: string | null;
  passage: string;
  source_url: string | null;
}

export interface AskResponse {
  answer: string;
  refused: boolean;
  citations: Citation[];
  disclaimer: string;
}

export type CardStatus = "loading-searching" | "loading-drafting" | "answered" | "refused" | "error";

export interface QACardData {
  id: string;
  question: string;
  status: CardStatus;
  answer?: string;
  citations?: Citation[];
  disclaimer?: string;
  isHistorical: boolean; // true = restored from a prior visit, above the session divider
}
