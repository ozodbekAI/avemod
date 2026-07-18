import { useQuery, type UseQueryOptions, type QueryKey } from "@tanstack/react-query";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";

/**
 * Стандартный wrapper над useQuery для страничных запросов.
 * - queryKey всегда содержит [account_id, date_from, date_to] + локальный ключ.
 * - кэшируется на клиенте (5 минут) для того же account+период.
 * - не запускается, если account не выбран.
 *
 * Это единственный канонический способ грузить данные страниц, чтобы
 * не палить десять тяжёлых эндпоинтов параллельно и не сбрасывать кэш
 * при смене вкладки.
 */
export function usePageQuery<T>(
  localKey: QueryKey,
  fetcher: (args: { accountId: number; dateFrom: string; dateTo: string }) => Promise<T>,
  opts: Omit<UseQueryOptions<T, unknown, T, QueryKey>, "queryKey" | "queryFn"> = {}
) {
  const { activeId } = useAccounts();
  const { from, to } = useDateRange();

  return useQuery<T, unknown, T, QueryKey>({
    queryKey: ["page", activeId, from, to, ...(localKey as unknown[])],
    queryFn: () => fetcher({ accountId: activeId!, dateFrom: from, dateTo: to }),
    enabled: !!activeId && !!from && !!to && (opts.enabled ?? true),
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
    ...opts,
  });
}
