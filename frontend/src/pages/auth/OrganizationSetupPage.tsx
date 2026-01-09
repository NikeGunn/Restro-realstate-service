import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/auth';
import { organizationsApi } from '@/services/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { Building2, UtensilsCrossed, ArrowRight, MessageSquare } from 'lucide-react';

export function OrganizationSetupPage() {
  const { t } = useTranslation();
  const [step, setStep] = useState<'type' | 'details'>('type');
  const [businessType, setBusinessType] = useState<'restaurant' | 'real_estate' | null>(null);
  const [orgName, setOrgName] = useState('');
  const [loading, setLoading] = useState(false);
  const { setCurrentOrganization } = useAuthStore();
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleSelectType = (type: 'restaurant' | 'real_estate') => {
    setBusinessType(type);
    setStep('details');
  };

  const handleCreateOrganization = async () => {
    if (!orgName.trim() || !businessType) return;

    setLoading(true);
    try {
      const org = await organizationsApi.create({
        name: orgName,
        business_type: businessType,
      });

      // Fetch full org details
      const fullOrg = await organizationsApi.get(org.id);
      setCurrentOrganization(fullOrg);

      toast({
        title: t('organization.created'),
        description: t('organization.createdDescription'),
      });

      navigate('/dashboard');
    } catch (error) {
      console.error('Error creating organization:', error);
      toast({
        variant: 'destructive',
        title: t('organization.createError'),
        description: t('organization.createErrorDescription'),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
      <div className="w-full max-w-2xl">
        {/* Header with Logo and Language Switcher */}
        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-8 w-8 text-primary" />
            <span className="font-bold text-xl">ChatPlatform</span>
          </div>
          <LanguageSwitcher variant="compact" />
        </div>

        {step === 'type' ? (
          <div className="space-y-6">
            <div className="text-center">
              <h1 className="text-3xl font-bold">{t('organization.title')}</h1>
              <p className="text-muted-foreground mt-2">{t('organization.subtitle')}</p>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              {/* Restaurant Card */}
              <Card
                className={`cursor-pointer transition-all hover:shadow-lg hover:border-primary ${
                  businessType === 'restaurant' ? 'border-primary shadow-lg' : ''
                }`}
                onClick={() => handleSelectType('restaurant')}
              >
                <CardHeader className="text-center pb-2">
                  <div className="mx-auto p-4 bg-orange-100 rounded-full w-fit mb-2">
                    <UtensilsCrossed className="h-10 w-10 text-orange-600" />
                  </div>
                  <CardTitle>{t('organization.restaurant')}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-center">
                    {t('organization.restaurantDescription')}
                  </CardDescription>
                </CardContent>
              </Card>

              {/* Real Estate Card */}
              <Card
                className={`cursor-pointer transition-all hover:shadow-lg hover:border-primary ${
                  businessType === 'real_estate' ? 'border-primary shadow-lg' : ''
                }`}
                onClick={() => handleSelectType('real_estate')}
              >
                <CardHeader className="text-center pb-2">
                  <div className="mx-auto p-4 bg-blue-100 rounded-full w-fit mb-2">
                    <Building2 className="h-10 w-10 text-blue-600" />
                  </div>
                  <CardTitle>{t('organization.realEstate')}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-center">
                    {t('organization.realEstateDescription')}
                  </CardDescription>
                </CardContent>
              </Card>
            </div>
          </div>
        ) : (
          <Card className="shadow-lg">
            <CardHeader className="text-center">
              <div className="flex justify-center mb-4">
                <div className={`p-3 rounded-full ${
                  businessType === 'restaurant' ? 'bg-orange-100' : 'bg-blue-100'
                }`}>
                  {businessType === 'restaurant' ? (
                    <UtensilsCrossed className={`h-8 w-8 text-orange-600`} />
                  ) : (
                    <Building2 className={`h-8 w-8 text-blue-600`} />
                  )}
                </div>
              </div>
              <CardTitle className="text-2xl">{t('organization.createTitle')}</CardTitle>
              <CardDescription>{t('organization.createDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="orgName">{t('organization.name')}</Label>
                <Input
                  id="orgName"
                  placeholder={t('organization.namePlaceholder')}
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  autoFocus
                />
              </div>

              <div className="space-y-2">
                <Label>{t('organization.businessType')}</Label>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant={businessType === 'restaurant' ? 'default' : 'outline'}
                    onClick={() => setBusinessType('restaurant')}
                    className="flex-1"
                  >
                    <UtensilsCrossed className="h-4 w-4 mr-2" />
                    {t('organization.restaurant')}
                  </Button>
                  <Button
                    type="button"
                    variant={businessType === 'real_estate' ? 'default' : 'outline'}
                    onClick={() => setBusinessType('real_estate')}
                    className="flex-1"
                  >
                    <Building2 className="h-4 w-4 mr-2" />
                    {t('organization.realEstate')}
                  </Button>
                </div>
              </div>

              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => setStep('type')}
                  className="flex-1"
                >
                  {t('common.back')}
                </Button>
                <Button
                  onClick={handleCreateOrganization}
                  disabled={loading || !orgName.trim()}
                  className="flex-1"
                >
                  {loading ? t('common.loading') : t('organization.createButton')}
                  {!loading && <ArrowRight className="h-4 w-4 ml-2" />}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
