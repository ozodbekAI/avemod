import { useEffect, useState } from "react";
import { Code2 } from "lucide-react";

import type { ProblemRuleVersionCreatePayload } from "@/lib/problem-rules";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import {
  Field,
  type AdvancedOverrides,
  jsonTextsFromPayload,
} from "./ProblemRulesAdminShared";

export function AdvancedJsonEditor({
  payload,
  advancedOpen,
  onAdvancedOpenChange,
  onApply,
  error,
  onError,
}: {
  payload: ProblemRuleVersionCreatePayload;
  advancedOpen: boolean;
  onAdvancedOpenChange: (open: boolean) => void;
  onApply: (overrides: AdvancedOverrides) => void;
  error: string | null;
  onError: (error: string | null) => void;
}) {
  const [texts, setTexts] = useState(() => jsonTextsFromPayload(payload));
  useEffect(() => {
    setTexts(jsonTextsFromPayload(payload));
  }, [payload]);
  const apply = () => {
    try {
      const overrides: AdvancedOverrides = {
        condition_json: JSON.parse(texts.condition_json),
        impact_formula_json: JSON.parse(texts.impact_formula_json),
        severity_formula_json: JSON.parse(texts.severity_formula_json),
        confidence_formula_json: JSON.parse(texts.confidence_formula_json),
        recheck_rule_json: JSON.parse(texts.recheck_rule_json),
        evidence_template_json: JSON.parse(texts.evidence_template_json),
      };
      onApply(overrides);
    } catch (exc) {
      onError(exc instanceof Error ? exc.message : "Некорректный JSON");
    }
  };
  return (
    <div className="rounded-md border p-3" data-admin-rule-advanced-json="1">
      <label className="flex items-center gap-2 text-sm font-medium">
        <Checkbox
          checked={advancedOpen}
          onCheckedChange={(checked) => onAdvancedOpenChange(Boolean(checked))}
        />
        <span className="inline-flex items-center gap-2">
          <Code2 className="h-4 w-4" /> Расширенный режим
        </span>
      </label>
      <div className="mt-1 text-xs text-muted-foreground">
        JSON скрыт в обычном сценарии. Включайте только для редких формул,
        которые пока нельзя собрать визуально.
      </div>
      {advancedOpen ? (
        <div className="mt-3">
          <Alert className="mb-3">
            <Code2 className="h-4 w-4" />
            <AlertTitle>JSON только для технических администраторов</AlertTitle>
            <AlertDescription>
              Обычный сценарий создаётся блоками выше. Этот режим нужен для редких
              формул, которые пока нельзя собрать визуально.
            </AlertDescription>
          </Alert>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(texts).map(([key, value]) => (
              <Field key={key} label={key}>
                <Textarea
                  rows={7}
                  className="font-mono text-xs"
                  value={value}
                  onChange={(event) =>
                    setTexts({ ...texts, [key]: event.target.value })
                  }
                />
              </Field>
            ))}
          </div>
          {error && <div className="mt-2 text-sm text-destructive">{error}</div>}
          <Button className="mt-3" variant="outline" onClick={apply}>
            <Code2 className="mr-1.5 h-4 w-4" />
            Применить JSON
          </Button>
        </div>
      ) : null}
    </div>
  );
}
