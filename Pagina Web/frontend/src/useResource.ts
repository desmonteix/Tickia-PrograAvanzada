import { useEffect, useState } from 'react';
import api, { errorMessage } from './api';
import { useCallback } from 'react';

export function useResource<T>(path: string, timeout = 20000) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api
      .get<T>(path, { signal: controller.signal, timeout })
      .then((response) => {
        if (!controller.signal.aborted) {
          setData(response.data);
          setError('');
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(errorMessage(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, revision, timeout]);
  const refresh = useCallback(() => {
    setLoading(true);
    setError('');
    setRevision((value) => value + 1);
  }, []);
  return { data, loading, error, refresh };
}
