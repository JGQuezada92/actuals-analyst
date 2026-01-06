import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function SettingsPage() {
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Settings configuration coming soon...
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

