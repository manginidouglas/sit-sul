# Protocolo de qualidade e robustez

Antes da narrativa, por indicador devem ser publicados cobertura, período, zeros, ausentes, não aplicáveis, média, mediana, desvio, P1/P5/P25/P50/P75/P95/P99, extremos brutos/tratados, winsorizados, UF/porte, top/bottom e flags; o 1% superior e inferior exige inspeção manual.

Sanity checks cobrem correlação com população; pequenos metropolitanos; fronteiras com SP/MS; capitais, polos e isolados; múltiplos aeroportos; rodovia na sede; portos; DEC/FEC e métodos territoriais; missing por UF/porte/tipo.

Comparar a base com: sem winsorização; mercado sem `log1p`; e onze pesos iguais na Infraestrutura. Registrar Spearman, mudança mediana/máxima, top 20/50 e sensíveis. Como os dados integrais ainda não foram coletados, não há coeficientes nem achados a reportar; qualquer número seria fictício.
